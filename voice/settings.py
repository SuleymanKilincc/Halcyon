"""
Voice pipeline configuration.

Every knob that affects perceived latency or turn-taking lives here so it can
be tuned without touching the pipeline logic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = BASE_DIR / "models"

# Whisper and Silero both operate on 16 kHz mono audio. Do not change this
# without changing the VAD frame size below: Silero only accepts exactly
# 512 samples per frame at 16 kHz.
SAMPLE_RATE = 16000
VAD_FRAME_SAMPLES = 512
VAD_FRAME_MS = VAD_FRAME_SAMPLES * 1000 // SAMPLE_RATE  # 32 ms


@dataclass
class VADSettings:
    """Endpointing: deciding when the user started and stopped speaking."""

    # Silero speech probability above which a frame counts as speech.
    threshold: float = 0.5

    # How much continuous speech is required before we accept that a turn
    # started. Filters out coughs, keyboard clicks and door slams.
    min_speech_ms: int = 160

    # How much silence ends the turn. This is the single most important
    # latency knob: it is dead time added to every single response.
    # Below ~350 ms the user gets cut off mid-sentence on natural pauses.
    min_silence_ms: int = 480

    # Audio kept from before speech was detected, so the first phoneme is not
    # clipped off the front of the utterance.
    pre_roll_ms: int = 320

    # Hard ceiling on a single utterance, so a stuck VAD cannot record forever.
    max_utterance_ms: int = 30_000


@dataclass
class BargeInSettings:
    """Interrupting Halcyon mid-sentence."""

    enabled: bool = True

    # Barge-in uses a stricter threshold than normal listening, because while
    # Halcyon is speaking the microphone also hears Halcyon. Without acoustic
    # echo cancellation this is what keeps the assistant from interrupting
    # itself through the laptop speakers.
    threshold: float = 0.85

    # Continuous speech required to actually cut playback off.
    min_speech_ms: int = 280

    # Grace period after playback starts during which barge-in is ignored,
    # covering the speaker/driver ramp-up transient.
    warmup_ms: int = 250


@dataclass
class STTSettings:
    """faster-whisper (CTranslate2) speech recognition."""

    # distil-large-v3 is English-only. For Turkish + English use large-v3-turbo
    # (~1.6 GB VRAM in int8_float16) or small (~0.5 GB) on a tighter budget.
    model: str = os.getenv("HALCYON_STT_MODEL", "large-v3-turbo")

    # "cuda" | "cpu" | "auto"
    device: str = os.getenv("HALCYON_STT_DEVICE", "auto")

    # int8_float16 on GPU is the accuracy/VRAM sweet spot for Ada cards.
    compute_type_cuda: str = "int8_float16"
    compute_type_cpu: str = "int8"

    # None = autodetect per utterance. Autodetection costs ~50 ms and is
    # unreliable on very short utterances, so a fixed language is faster and
    # more accurate when you know you will only speak one.
    language: str | None = os.getenv("HALCYON_STT_LANGUAGE") or None

    # Restrict autodetection to languages we actually have voices for.
    candidate_languages: tuple[str, ...] = ("tr", "en")

    # Measured on this machine (8 physical / 16 logical cores): pinning to the
    # physical core count is worth ~25-30% over CTranslate2's own default.
    cpu_threads: int = 8

    # The choices below were measured with `python -m bench.stt_eval --compare`,
    # which replays identical synthetic audio through each setting. The
    # resulting table, and why each choice was made, is in docs/VOICE.md
    # ("Speech-recognition quality"). Numbers are kept there, not here, so they
    # exist in exactly one place.

    # Greedy decoding: beam search (5) gave no consistent accuracy gain and
    # added ~35 ms per utterance.
    beam_size: int = 1

    # Second-stage VAD inside faster-whisper, on top of our own endpointing:
    # ours decides when a turn starts and ends, this one removes non-speech
    # inside the utterance before Whisper sees it. It is what stops Whisper
    # "transcribing" room noise, breathing and hum as "Thank you." or "you".
    # The model ships with faster-whisper; nothing is downloaded.
    vad_filter: bool = True

    # When Whisper detects a language outside candidate_languages, treat the
    # utterance as not understood and drop it, so the language model never
    # acts on it and Halcyon stays silent - the pipeline's rule for anything it
    # is not sure was speech. In the benchmark this only happened on very
    # noisy audio, every such clip was unintelligible, and decoding it again
    # in Turkish produced Turkish nonsense instead. When False, the original
    # behaviour applies: the text is kept and only relabelled.
    drop_other_languages: bool = True

    # Drop transcripts that are exactly one of Whisper's well-known phantom
    # phrases (PHANTOM_PHRASES in voice/stt.py). A second line of defence:
    # in the benchmark the VAD above already removed every phantom.
    phantom_filter: bool = True

    # Words to bias recognition towards (faster-whisper `hotwords`). Helped
    # Turkish clearly in far-field and noisy speech, including on sentences
    # that contain none of these words.
    hotwords: str | None = "Python Halcyon masaüstü"

    # Utterances shorter than this are almost always noise that slipped past
    # the VAD. Transcribing them wastes a GPU round trip.
    min_utterance_ms: int = 240


@dataclass
class TTSSettings:
    """Piper (ONNX) speech synthesis."""

    voices: dict[str, str] = field(
        default_factory=lambda: {
            # Verified present in rhasspy/piper-voices.
            "tr": "tr_TR-dfki-medium",
            "en": "en_US-ryan-medium",
        }
    )
    default_language: str = "tr"

    # 1.0 = the voice's native speed. Below 1.0 is faster in Piper's
    # length_scale convention.
    length_scale: float = 1.0
    noise_scale: float = 0.667
    noise_w: float = 0.8

    # Sentences are synthesised and queued for playback one at a time, so
    # audio starts while the LLM is still generating. This is the difference
    # between "first audio after the full answer" and "first audio in ~1 s".
    stream_by_sentence: bool = True

    # A first chunk shorter than this is held back and merged with the next
    # one: single-word fragments ("Tamam.") sound clipped when spoken alone.
    min_sentence_chars: int = 12


@dataclass
class VoiceSettings:
    vad: VADSettings = field(default_factory=VADSettings)
    barge_in: BargeInSettings = field(default_factory=BargeInSettings)
    stt: STTSettings = field(default_factory=STTSettings)
    tts: TTSSettings = field(default_factory=TTSSettings)

    input_device: int | str | None = None   # None = system default
    output_device: int | str | None = None

    models_dir: Path = MODELS_DIR

    def __post_init__(self) -> None:
        self.models_dir = Path(self.models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)


DEFAULT = VoiceSettings()
