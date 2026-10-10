"""
The full-duplex voice loop.

Ties VAD, STT and TTS together into a conversation:

    listen -> endpoint -> transcribe -> [your handler] -> speak

The two properties that separate this from the previous push-to-talk
implementation:

* **Streaming.** The handler yields text as it is generated; each completed
  sentence is synthesised and played while the rest is still being produced.
  Time to first audio stops depending on total answer length.
* **Barge-in.** The microphone stays open while Jarvis speaks. Sustained
  speech cuts playback off mid-word and starts a new turn.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from enum import Enum, auto

import numpy as np

from voice.audio import MicStream, Player
from voice.settings import DEFAULT, VoiceSettings
from voice.stt import Transcriber, Transcript
from voice.tts import SentenceStreamer, Synthesizer
from voice.vad import BargeInDetector, SpeechDetector, VADEvent

# A handler receives the user's transcript and yields response text as it is
# produced. Yielding a single string at the end also works; it just gives up
# the streaming latency win.
ResponseHandler = Callable[[Transcript], Iterator[str]]


class State(Enum):
    IDLE = auto()
    LISTENING = auto()
    TRANSCRIBING = auto()
    RESPONDING = auto()
    SPEAKING = auto()


@dataclass
class TurnTimings:
    """Wall-clock breakdown of one turn, for the latency benchmark."""

    speech_end: float = 0.0
    transcribed: float = 0.0
    first_token: float = 0.0
    first_audio: float = 0.0
    finished: float = 0.0

    @staticmethod
    def _ms(start: float, end: float) -> int:
        # round, not int: int() truncates, and floating-point subtraction makes
        # 10.42 - 10.3 come out as 0.11999..., which int() reports as 119 ms.
        return round((end - start) * 1000) if start and end else -1

    @property
    def stt_ms(self) -> int:
        return self._ms(self.speech_end, self.transcribed)

    @property
    def llm_first_token_ms(self) -> int:
        return self._ms(self.transcribed, self.first_token)

    @property
    def tts_ms(self) -> int:
        return self._ms(self.first_token, self.first_audio)

    @property
    def total_to_first_audio_ms(self) -> int:
        """The number that decides whether this feels like a conversation."""
        return self._ms(self.speech_end, self.first_audio)


@dataclass
class VoiceEvents:
    """Optional callbacks, so a GUI can render state without polling."""

    on_state: Callable[[State], None] | None = None
    on_speech_start: Callable[[], None] | None = None
    on_user: Callable[[Transcript], None] | None = None
    on_response_delta: Callable[[str], None] | None = None
    on_response_done: Callable[[str], None] | None = None
    on_barge_in: Callable[[], None] | None = None
    on_timings: Callable[[TurnTimings], None] | None = None
    on_error: Callable[[Exception], None] | None = None

    def emit(self, name: str, *args: object) -> None:
        callback = getattr(self, name, None)
        if callback is None:
            return
        try:
            callback(*args)
        except Exception:  # noqa: BLE001 - a broken UI callback must not kill the loop
            pass


class VoiceLoop:
    def __init__(
        self,
        handler: ResponseHandler,
        settings: VoiceSettings | None = None,
        events: VoiceEvents | None = None,
    ) -> None:
        self.settings = settings or DEFAULT
        self.handler = handler
        self.events = events or VoiceEvents()

        self.state = State.IDLE
        self._stop = threading.Event()
        self._interrupted = threading.Event()

        self.transcriber = Transcriber(self.settings.stt)
        self.synthesizer = Synthesizer(self.settings.tts, self.settings.models_dir)
        self.detector = SpeechDetector(self.settings.vad)
        self.barge_in = BargeInDetector(self.settings.barge_in)
        self.player: Player | None = None

        self._speaking_since = 0.0
        self.last_timings: TurnTimings | None = None

    # ------------------------------------------------------------------ setup

    def prepare(self) -> None:
        """
        Load every model before the first turn.

        Without this the user's opening sentence silently absorbs several
        seconds of one-time model loading, which is then blamed on the
        assistant being slow rather than on startup.
        """
        self.transcriber.warmup()
        self.synthesizer.preload()
        self.player = Player(self.synthesizer.sample_rate, self.settings.output_device)
        self.player.start()

    def _set_state(self, state: State) -> None:
        self.state = state
        self.events.emit("on_state", state)

    # ------------------------------------------------------------------- loop

    def run(self) -> None:
        if self.player is None:
            self.prepare()

        with MicStream(self.settings.input_device) as mic:
            self._set_state(State.LISTENING)
            for frame in mic.frames(self._stop):
                if self.state is State.SPEAKING:
                    self._check_barge_in(frame)
                    continue
                if self.state is not State.LISTENING:
                    continue

                event, utterance = self.detector.push(frame)
                if event is VADEvent.SPEECH_START:
                    self.events.emit("on_speech_start")
                elif event is VADEvent.SPEECH_END and utterance is not None:
                    self._handle_turn(utterance.audio, mic)
                    self._set_state(State.LISTENING)

    def stop(self) -> None:
        self._stop.set()
        self._interrupted.set()
        if self.player is not None:
            self.player.stop()

    def close(self) -> None:
        self.stop()
        if self.player is not None:
            self.player.close()
            self.player = None

    # ------------------------------------------------------------------- turn

    def _handle_turn(self, audio: np.ndarray, mic: MicStream) -> None:
        timings = TurnTimings(speech_end=time.perf_counter())
        self._interrupted.clear()

        self._set_state(State.TRANSCRIBING)
        try:
            transcript = self.transcriber.transcribe(audio)
        except Exception as exc:  # noqa: BLE001
            self.events.emit("on_error", exc)
            return
        timings.transcribed = time.perf_counter()

        if transcript.is_empty:
            # Noise that cleared the VAD but carried no words. Say nothing: an
            # assistant that answers coughs is worse than one that occasionally
            # misses a quiet sentence.
            return
        self.events.emit("on_user", transcript)

        language = transcript.language or self.settings.tts.default_language
        streamer = SentenceStreamer(self.settings.tts.min_sentence_chars)
        spoken_any = False
        full_response: list[str] = []

        self._set_state(State.RESPONDING)
        # Held by name so it can be closed explicitly below. Breaking out of a
        # `for` over a generator does NOT release the resources it holds; for a
        # streamed LLM response that leaves the server generating tokens nobody
        # will read, and the next turn queues behind it. Barge-in takes this
        # path every single time, so it is the normal case, not an edge case.
        response_stream = self.handler(transcript)
        try:
            for delta in response_stream:
                if self._interrupted.is_set():
                    break
                if not delta:
                    continue
                if not timings.first_token:
                    timings.first_token = time.perf_counter()
                full_response.append(delta)
                self.events.emit("on_response_delta", delta)

                for sentence in streamer.push(delta):
                    if self._interrupted.is_set():
                        break
                    spoken_any = self._speak(sentence, language, timings) or spoken_any

            if not self._interrupted.is_set():
                for sentence in streamer.flush():
                    spoken_any = self._speak(sentence, language, timings) or spoken_any
        except Exception as exc:  # noqa: BLE001
            self.events.emit("on_error", exc)
        finally:
            close = getattr(response_stream, "close", None)
            if close is not None:
                close()

        if spoken_any and self.player is not None and not self._interrupted.is_set():
            self.player.wait_until_idle(timeout=120)

        timings.finished = time.perf_counter()
        self.last_timings = timings
        self.events.emit("on_response_done", "".join(full_response))
        self.events.emit("on_timings", timings)

        self._set_state(State.LISTENING)
        self.barge_in.reset()
        self.detector.reset()
        # Anything the microphone captured while Jarvis was talking is either
        # Jarvis itself or barge-in audio that has already been handled. Either
        # way it must not be transcribed as the next user turn.
        mic.drain()

    def _speak(self, sentence: str, language: str, timings: TurnTimings) -> bool:
        if self.player is None or self._interrupted.is_set():
            return False
        chunks = list(self.synthesizer.synthesize(sentence, language))
        if not chunks:
            return False
        if not timings.first_audio:
            timings.first_audio = time.perf_counter()
        if self.state is not State.SPEAKING:
            self._speaking_since = time.perf_counter()
            self._set_state(State.SPEAKING)
            self.barge_in.reset()
        for chunk in chunks:
            if self._interrupted.is_set():
                return True
            self.player.play(chunk)
        return True

    # --------------------------------------------------------------- barge-in

    def _check_barge_in(self, frame: np.ndarray) -> None:
        if not self.settings.barge_in.enabled:
            return
        elapsed_ms = (time.perf_counter() - self._speaking_since) * 1000
        if elapsed_ms < self.settings.barge_in.warmup_ms:
            return
        if not self.barge_in.push(frame):
            return

        self._interrupted.set()
        if self.player is not None:
            self.player.stop()
        self.barge_in.reset()
        self.detector.reset()
        self.events.emit("on_barge_in")
        self._set_state(State.LISTENING)


def echo_handler(transcript: Transcript) -> Iterator[str]:
    """A handler with no LLM behind it, for exercising the audio path alone."""
    yield f"Sunu duydum: {transcript.text}"
