"""
Speech-to-text via faster-whisper (CTranslate2).

Fully local: no audio leaves the machine. This replaces the previous
pipeline's ``recognizer.recognize_google(...)``, which sent every utterance
to a Google endpoint and stopped working without an internet connection.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import numpy as np

from voice.settings import SAMPLE_RATE, STTSettings

# Whisper checkpoints large enough that running them on CPU turns a
# sub-second transcription into a multi-second one.
_LARGE_MODELS = ("large", "large-v1", "large-v2", "large-v3", "large-v3-turbo", "turbo", "medium")

# Measured on this machine, CPU / int8 / 8 threads, on a 2.6 s utterance:
#   tiny  269 ms   base  498 ms   small  1646 ms
# and on GPU the same work is a fraction of that. "base" is the largest
# checkpoint that still fits the sub-1.5 s end-to-end budget on CPU alone.
_CPU_FALLBACK = "base"


@dataclass
class Transcript:
    text: str
    language: str
    language_probability: float
    duration_ms: int      # length of the audio
    latency_ms: int       # wall-clock time we spent transcribing it

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


def load_cuda_runtime() -> None:
    """
    Make the CUDA math libraries (cuBLAS, cuDNN) loadable for CTranslate2.

    faster-whisper does not ship cuBLAS or cuDNN; on Windows it finds them only
    if something has already loaded them into the process. PyTorch's CUDA build
    bundles exactly those DLLs and loads them on import. Without this call, GPU
    transcription fails with "cublas64_12.dll is not found" - and it used to
    work only by accident, because some other module happened to import torch
    first. Calling it explicitly makes the dependency visible and independent
    of import order.
    """
    try:
        import torch  # noqa: F401  (imported for its side effect)
    except ImportError as exc:
        raise RuntimeError(
            "GPU speech recognition needs the CUDA libraries that come with "
            "PyTorch's CUDA build, and torch is not installed."
        ) from exc


def resolve_device(requested: str) -> str:
    if requested != "auto":
        return requested
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:  # noqa: BLE001 - torch is optional for CPU-only setups
        return "cpu"


def resolve_model(configured: str, device: str) -> str:
    """
    Pick a checkpoint that can actually keep up on the resolved device.

    A large checkpoint on CPU is not a slower version of the same experience;
    it is a different product, because several seconds of transcription
    latency lands on every turn. When the user has not pinned a model
    explicitly, prefer a size the device can serve in well under a second.
    """
    if os.getenv("JARVIS_STT_MODEL"):
        return configured  # explicit choice wins, however slow
    if device == "cpu" and configured in _LARGE_MODELS:
        return _CPU_FALLBACK
    return configured


class Transcriber:
    def __init__(self, settings: STTSettings | None = None) -> None:
        from faster_whisper import WhisperModel

        self.settings = settings or STTSettings()
        self.device = resolve_device(self.settings.device)
        self.model_name = resolve_model(self.settings.model, self.device)
        if self.device == "cuda":
            load_cuda_runtime()
        self.compute_type = (
            self.settings.compute_type_cuda if self.device == "cuda"
            else self.settings.compute_type_cpu
        )

        if self.model_name != self.settings.model:
            # State the cost of the fallback rather than just the fact of it:
            # a quietly downgraded model is heard as "Jarvis mishears me",
            # which sends the user looking in entirely the wrong place.
            print(
                f"[stt] No CUDA device available, so '{self.settings.model}' would add "
                f"~1.5 s to every turn. Falling back to '{self.model_name}', which meets "
                f"the latency budget but is noticeably less accurate, especially in Turkish."
            )
            print("      Fix the GPU to get both. Set JARVIS_STT_MODEL to override.")

        started = time.perf_counter()
        self._model = WhisperModel(
            self.model_name,
            device=self.device,
            compute_type=self.compute_type,
            cpu_threads=self.settings.cpu_threads if self.device == "cpu" else 0,
        )
        self.load_seconds = time.perf_counter() - started

    def describe(self) -> str:
        threads = f", {self.settings.cpu_threads} threads" if self.device == "cpu" else ""
        return (f"faster-whisper {self.model_name} on {self.device} "
                f"({self.compute_type}{threads}), loaded in {self.load_seconds:.1f}s")

    def warmup(self) -> None:
        """
        Run one throwaway transcription.

        The first call allocates buffers and, on CUDA, compiles kernels — a
        cost of one to several seconds that would otherwise be paid by the
        user's first spoken sentence.
        """
        self._model.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32), beam_size=1)

    def transcribe(self, audio: np.ndarray, language: str | None = None) -> Transcript:
        duration_ms = int(len(audio) * 1000 / SAMPLE_RATE)
        if duration_ms < self.settings.min_utterance_ms:
            return Transcript("", language or "", 0.0, duration_ms, 0)

        started = time.perf_counter()
        segments, info = self._model.transcribe(
            np.asarray(audio, dtype=np.float32),
            language=language or self.settings.language,
            beam_size=self.settings.beam_size,
            vad_filter=self.settings.vad_filter,
            condition_on_previous_text=False,  # stops cross-turn hallucination loops
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        latency_ms = int((time.perf_counter() - started) * 1000)

        detected = getattr(info, "language", "") or ""
        probability = float(getattr(info, "language_probability", 0.0) or 0.0)

        # Whisper will confidently label a Turkish sentence as some unrelated
        # language on short audio. Constrain it to languages we can answer in.
        if detected and detected not in self.settings.candidate_languages:
            detected = self.settings.candidate_languages[0]
            probability = 0.0

        return Transcript(text, detected, probability, duration_ms, latency_ms)
