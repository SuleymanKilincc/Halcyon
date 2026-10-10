"""
Text-to-speech via Piper (ONNX).

Replaces pyttsx3/SAPI5. Two things matter here beyond voice quality:

* Synthesis is fast enough on CPU (measured ~21x realtime for the Turkish
  medium voice, ~5x for a "high" quality English voice) that it is never
  the bottleneck, so no GPU budget is spent on it.
* Text is consumed sentence by sentence, so playback can begin while the LLM
  is still generating the rest of the answer.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Iterable, Iterator
from pathlib import Path

import numpy as np

from voice.models import ensure_piper_voice
from voice.settings import TTSSettings

# A sentence boundary: terminal punctuation, any closing quote or bracket,
# then whitespace. Requiring the trailing whitespace is what keeps "3.5 GB"
# and "vb." from splitting mid-token.
_SPLIT = re.compile(r"(?<=[.!?…])[\"')\]]*(?=\s)")

# Text that should never be spoken aloud: code fences, inline code, URLs,
# and markdown emphasis markers. Reading these out loud is unlistenable.
_CODE_BLOCK = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`]*)`")
_URL = re.compile(r"https?://\S+")
_MARKDOWN = re.compile(r"[*_#>]+")


# What is said aloud in place of things that cannot be read out. These are
# spoken words, so they follow the language of the reply.
SPOKEN_PLACEHOLDERS = {
    "en": {"code": "code block", "url": "link"},
    "tr": {"code": "kod bloğu", "url": "bağlantı"},
}


def clean_for_speech(text: str, language: str = "en") -> str:
    """Strip markup that is meaningful on screen but noise when spoken."""
    words = SPOKEN_PLACEHOLDERS.get(language, SPOKEN_PLACEHOLDERS["en"])
    text = _CODE_BLOCK.sub(f" {words['code']} ", text)
    text = _INLINE_CODE.sub(r"\1", text)
    text = _URL.sub(f" {words['url']} ", text)
    text = _MARKDOWN.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


class SentenceStreamer:
    """
    Turns a stream of LLM text deltas into complete sentences.

    The whole point of the voice pipeline's responsiveness lives here: the
    first sentence is released the moment it is complete, rather than after
    the model has finished the entire answer.
    """

    def __init__(self, min_chars: int = 12) -> None:
        self.min_chars = min_chars
        self._buffer = ""

    def push(self, delta: str) -> list[str]:
        """Add a chunk of generated text; return any sentences now complete."""
        self._buffer += delta
        out: list[str] = []
        while True:
            cut = self._next_cut()
            if cut is None:
                break
            sentence = self._buffer[:cut].strip()
            self._buffer = self._buffer[cut:]
            if sentence:
                out.append(sentence)
        return out

    def _next_cut(self) -> int | None:
        """
        Offset to cut the buffer at, or None if nothing is ready yet.

        Short openers ("Tabii.", "Evet.") are merged forward rather than
        emitted alone: we skip past a boundary that would produce a fragment
        below ``min_chars`` and look for the next one. Spoken in isolation
        such fragments sound clipped, and each one also costs a separate
        synthesis round trip.
        """
        for match in _SPLIT.finditer(self._buffer):
            if len(self._buffer[:match.end()].strip()) >= self.min_chars:
                return match.end()
        return None

    def flush(self) -> list[str]:
        """Release whatever is left, complete sentence or not."""
        remaining = self._buffer.strip()
        self._buffer = ""
        return [remaining] if remaining else []


class Synthesizer:
    """Multi-language Piper wrapper. Voices are loaded lazily and cached."""

    def __init__(self, settings: TTSSettings | None = None, models_dir: Path | None = None) -> None:
        from voice.settings import MODELS_DIR

        self.settings = settings or TTSSettings()
        self.models_dir = Path(models_dir or MODELS_DIR)
        self._voices: dict[str, object] = {}
        self._lock = threading.Lock()
        self._sample_rate: int | None = None

    @property
    def sample_rate(self) -> int:
        if self._sample_rate is None:
            self._load(self.settings.default_language)
        assert self._sample_rate is not None
        return self._sample_rate

    def _load(self, language: str):  # noqa: ANN202
        language = language if language in self.settings.voices else self.settings.default_language
        with self._lock:
            if language in self._voices:
                return self._voices[language]
            from piper import PiperVoice

            files = ensure_piper_voice(self.settings.voices[language], self.models_dir)
            voice = PiperVoice.load(files.onnx, config_path=files.config)
            self._voices[language] = voice
            if self._sample_rate is None:
                self._sample_rate = int(voice.config.sample_rate)
            return voice

    def preload(self, languages: Iterable[str] | None = None) -> None:
        """Load voices up front so the first spoken reply is not delayed."""
        for language in (languages or self.settings.voices.keys()):
            self._load(language)

    def _synthesis_config(self):  # noqa: ANN202
        from piper import SynthesisConfig

        return SynthesisConfig(
            length_scale=self.settings.length_scale,
            noise_scale=self.settings.noise_scale,
            noise_w_scale=self.settings.noise_w,
            normalize_audio=True,
        )

    def synthesize(self, text: str, language: str | None = None) -> Iterator[np.ndarray]:
        """Yield int16 audio chunks for one piece of text."""
        language = language or self.settings.default_language
        spoken = clean_for_speech(text, language)
        if not spoken:
            return
        voice = self._load(language or self.settings.default_language)
        for chunk in voice.synthesize(spoken, syn_config=self._synthesis_config()):
            if self._sample_rate is None:
                self._sample_rate = chunk.sample_rate
            yield chunk.audio_int16_array

    def synthesize_all(self, text: str, language: str | None = None) -> np.ndarray:
        chunks = list(self.synthesize(text, language))
        if not chunks:
            return np.zeros(0, dtype=np.int16)
        return np.concatenate(chunks)
