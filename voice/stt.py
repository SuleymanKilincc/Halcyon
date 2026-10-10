"""
Speech-to-text via faster-whisper (CTranslate2).

Fully local: no audio leaves the machine. This replaces the previous
pipeline's ``recognizer.recognize_google(...)``, which sent every utterance
to a Google endpoint and stopped working without an internet connection.
"""

from __future__ import annotations

import os
import re
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
    # What Whisper itself detected, before it was constrained to the
    # candidate languages. Kept so a wrong detection stays visible.
    detected_language: str = ""
    # Why the text was discarded, if it was (e.g. "phantom").
    dropped: str = ""

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


# Whisper was trained on video subtitles, and on silence or noise it tends to
# "transcribe" the phrases that typically end a video. A transcript consisting
# of exactly one of these is dropped. Compared after lowercasing and removing
# punctuation. The first group was observed in bench/stt_eval.py on room noise,
# keyboard clicks, breathing and mains hum; the rest are widely reported.
#
# Trade-off: someone who really says only "thank you" is ignored. Acceptable
# for an assistant - it needs no reply - and far better than answering noise.
PHANTOM_PHRASES = frozenset({
    # observed here
    "you", "thank you", "e aí", "продолжение следует",
    # widely reported
    "thanks for watching", "thank you for watching", "thank you so much for watching",
    "please subscribe", "altyazı m k", "izlediğiniz için teşekkür ederim",
    "izlediğiniz için teşekkürler", "субтитры сделал dimatorzok",
})

# Download sizes of the checkpoints, measured from the local cache, so a first
# run can say what it is about to fetch before fetching it.
DOWNLOAD_SIZES = {"tiny": "75 MB", "base": "145 MB", "small": "465 MB", "large-v3-turbo": "1.6 GB"}


def normalise_for_match(text: str) -> str:
    text = re.sub(r"[^\w\s]", " ", text.lower())
    return " ".join(text.split())


def is_phantom(text: str) -> bool:
    return normalise_for_match(text) in PHANTOM_PHRASES


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
        options = dict(
            device=self.device,
            compute_type=self.compute_type,
            cpu_threads=self.settings.cpu_threads if self.device == "cpu" else 0,
        )
        # Local cache first. Without local_files_only, every start asks the
        # Hugging Face Hub whether a newer revision exists - a network request
        # on each launch of an assistant described as fully local, and data
        # spent on a metered connection. The network is used only when the
        # model has genuinely never been downloaded, and the size is announced.
        from huggingface_hub.errors import LocalEntryNotFoundError

        try:
            self._model = WhisperModel(self.model_name, local_files_only=True, **options)
        except LocalEntryNotFoundError:
            size = DOWNLOAD_SIZES.get(self.model_name, "unknown size")
            print(f"[stt] Whisper '{self.model_name}' is not downloaded yet; downloading ({size})...")
            self._model = WhisperModel(self.model_name, **options)
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
        audio = np.asarray(audio, dtype=np.float32)
        forced = language or self.settings.language
        text, info = self._decode(audio, forced)

        detected = getattr(info, "language", "") or ""
        final = detected
        probability = float(getattr(info, "language_probability", 0.0) or 0.0)

        # Whisper sometimes detects a language we cannot answer in - on noisy
        # Turkish it chose Portuguese, Russian, Chinese, and decoded the audio
        # in that language. In the benchmark that only ever happened on audio
        # that was unintelligible anyway, so it is treated as "not understood"
        # (see STTSettings.drop_other_languages). The label still becomes the
        # most probable candidate, so anything downstream stays in a language
        # Jarvis can speak.
        dropped = ""
        candidates = self.settings.candidate_languages
        if not forced and detected and detected not in candidates:
            probs = dict(getattr(info, "all_language_probs", None) or [])
            final = max(candidates, key=lambda code: probs.get(code, 0.0))
            probability = probs.get(final, 0.0)
            if self.settings.drop_other_languages and text:
                text, dropped = "", "unintelligible"

        if self.settings.phantom_filter and text and is_phantom(text):
            text, dropped = "", "phantom"

        latency_ms = int((time.perf_counter() - started) * 1000)
        return Transcript(text, final, probability, duration_ms, latency_ms,
                          detected_language=detected, dropped=dropped)

    def _decode(self, audio: np.ndarray, language: str | None):  # noqa: ANN202
        segments, info = self._model.transcribe(
            audio,
            language=language,
            beam_size=self.settings.beam_size,
            vad_filter=self.settings.vad_filter,
            hotwords=self.settings.hotwords,
            condition_on_previous_text=False,  # stops cross-turn hallucination loops
        )
        return " ".join(segment.text.strip() for segment in segments).strip(), info
