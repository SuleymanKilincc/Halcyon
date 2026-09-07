"""
Voice activity detection and endpointing.

Silero VAD gives a per-frame speech probability; this module turns that into
turn boundaries — when the user started talking and, more importantly, when
they stopped. The stop decision is on the critical latency path: every
millisecond of trailing silence we wait for is a millisecond of dead air the
user experiences on every single turn.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass
from enum import Enum, auto

import numpy as np

from voice.settings import SAMPLE_RATE, VAD_FRAME_MS, VAD_FRAME_SAMPLES, VADSettings


class VADEvent(Enum):
    NONE = auto()
    SPEECH_START = auto()
    SPEECH_END = auto()


@dataclass
class Utterance:
    audio: np.ndarray          # float32 in [-1, 1], ready for Whisper
    duration_ms: int


def _to_float32(frame: np.ndarray) -> np.ndarray:
    if frame.dtype == np.float32:
        return frame
    return frame.astype(np.float32) / 32768.0


class SpeechDetector:
    """
    Frame-by-frame endpointer.

    Feed it 512-sample frames; it returns an event per frame and, on
    SPEECH_END, the complete utterance including pre-roll.
    """

    def __init__(self, settings: VADSettings | None = None, threshold: float | None = None) -> None:
        from silero_vad import load_silero_vad  # imported late: pulls in torch

        self.settings = settings or VADSettings()
        self.threshold = self.settings.threshold if threshold is None else threshold
        self._model = load_silero_vad()

        self._speech_frames = _ms_to_frames(self.settings.min_speech_ms)
        self._silence_frames = _ms_to_frames(self.settings.min_silence_ms)
        self._max_frames = _ms_to_frames(self.settings.max_utterance_ms)

        # Pre-roll ring buffer: audio from just before the VAD fired, so the
        # first consonant of the utterance is not clipped.
        self._preroll: collections.deque[np.ndarray] = collections.deque(
            maxlen=max(1, _ms_to_frames(self.settings.pre_roll_ms))
        )

        self.reset()

    def reset(self) -> None:
        self._in_speech = False
        self._speech_run = 0
        self._silence_run = 0
        self._buffer: list[np.ndarray] = []
        self._preroll.clear()
        # Silero is stateful across frames; a stale state from the previous
        # turn makes the first frames of the next one unreliable.
        if hasattr(self._model, "reset_states"):
            self._model.reset_states()

    @property
    def in_speech(self) -> bool:
        return self._in_speech

    def probability(self, frame: np.ndarray) -> float:
        import torch

        if len(frame) != VAD_FRAME_SAMPLES:
            raise ValueError(
                f"Silero VAD requires exactly {VAD_FRAME_SAMPLES} samples at "
                f"{SAMPLE_RATE} Hz, got {len(frame)}"
            )
        audio = _to_float32(frame)
        with torch.no_grad():
            return float(self._model(torch.from_numpy(audio), SAMPLE_RATE).item())

    def push(self, frame: np.ndarray) -> tuple[VADEvent, Utterance | None]:
        """Process one frame and report whether a turn boundary was crossed."""
        audio = _to_float32(frame)
        is_speech = self.probability(frame) >= self.threshold

        if not self._in_speech:
            self._preroll.append(audio)
            if is_speech:
                self._speech_run += 1
                if self._speech_run >= self._speech_frames:
                    self._in_speech = True
                    self._silence_run = 0
                    self._buffer = list(self._preroll)
                    self._preroll.clear()
                    return VADEvent.SPEECH_START, None
            else:
                self._speech_run = 0
            return VADEvent.NONE, None

        self._buffer.append(audio)
        if is_speech:
            self._silence_run = 0
        else:
            self._silence_run += 1
            if self._silence_run >= self._silence_frames:
                return VADEvent.SPEECH_END, self._finish()

        if len(self._buffer) >= self._max_frames:
            return VADEvent.SPEECH_END, self._finish()

        return VADEvent.NONE, None

    def _finish(self) -> Utterance:
        audio = np.concatenate(self._buffer) if self._buffer else np.zeros(0, dtype=np.float32)
        # Trim the trailing silence we deliberately waited through: Whisper
        # sometimes hallucinates filler text over long silent tails.
        tail = self._silence_run * VAD_FRAME_SAMPLES
        if tail and len(audio) > tail:
            audio = audio[:-tail]
        duration_ms = int(len(audio) * 1000 / SAMPLE_RATE)
        self.reset()
        return Utterance(audio=audio, duration_ms=duration_ms)


class BargeInDetector:
    """
    A deliberately trigger-shy detector used only while Jarvis is speaking.

    It is a separate object from the main detector, with its own threshold and
    its own Silero state, because the two answer different questions: the main
    one asks "is this speech?", this one asks "is this speech loud and
    sustained enough that it is almost certainly not our own voice coming back
    through the speakers?".
    """

    def __init__(self, settings=None) -> None:  # noqa: ANN001
        from silero_vad import load_silero_vad

        from voice.settings import BargeInSettings

        self.settings = settings or BargeInSettings()
        self._model = load_silero_vad()
        self._needed = _ms_to_frames(self.settings.min_speech_ms)
        self._run = 0

    def reset(self) -> None:
        self._run = 0
        if hasattr(self._model, "reset_states"):
            self._model.reset_states()

    def push(self, frame: np.ndarray) -> bool:
        """Return True once sustained speech has been observed."""
        import torch

        audio = _to_float32(frame)
        with torch.no_grad():
            prob = float(self._model(torch.from_numpy(audio), SAMPLE_RATE).item())
        if prob >= self.settings.threshold:
            self._run += 1
        else:
            self._run = 0
        return self._run >= self._needed


def _ms_to_frames(ms: int) -> int:
    return max(1, round(ms / VAD_FRAME_MS))
