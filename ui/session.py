"""
What the window talks to: one conversation with the assistant, as a stream of events.

The window (ui/app.py) knows nothing about models, microphones or tools. It calls three things
here - send a typed message, turn the microphone on, turn it off - and draws the events that
come back. Every event is a small dict that becomes JSON for the page:

    {"type": "state", "state": "loading" | "ready" | "listening" | "transcribing" | "thinking"
                                | "speaking" | "error", "detail": "..."}
    {"type": "user", "text": "...", "via": "text" | "voice"}
    {"type": "assistant_start"}
    {"type": "delta", "text": "..."}          (the reply as it is generated)
    {"type": "assistant_done", "status": "mode: general | ..."}
    {"type": "info", "model": "...", "hardware": "...", "mode": "general"}
    {"type": "mic", "on": true | false}       (the microphone really is on or off now)
    {"type": "error", "message": "..."}

The work happens on background threads, so the window never freezes while a model loads or a
reply is written. Pure Python with no window code, so it is tested without one
(tests/test_ui_session.py); the model, the handler and the voice loop are injected.

The microphone is opened only when the user presses the button: nothing here opens it by itself.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

Emit = Callable[[dict], None]

# Voice loop states, as the page names them (voice.pipeline.State is mapped by name).
VOICE_STATES = {"IDLE": "ready", "LISTENING": "listening", "TRANSCRIBING": "transcribing",
                "RESPONDING": "thinking", "SPEAKING": "speaking"}


@dataclass
class Assistant:
    """What a session needs, built once: the model client, the handler that answers, and the rest."""

    llm: Any                                  # core.llm.SpeechLLM
    handler: Callable[[Any], Iterator[str]]   # transcript -> text deltas (ModeController.handler)
    controller: Any = None                    # core.router.ModeController, or None
    profile: Any = None
    hardware: Any = None
    make_voice_loop: Callable[[Any, Any], Any] | None = None   # (handler, events) -> VoiceLoop
    describe: dict = field(default_factory=dict)


def build_assistant() -> Assistant:
    """The real assistant, built the way `python -m voice.cli --llm` builds it."""
    from core.fit import fit_to_gpu
    from core.hardware import detect
    from core.llm import check_model_available, installed_models
    from core.profiles import apply_to_voice_settings, resolve
    from core.voice_tools import get_voice_tools
    from voice.cli import make_llm_handler
    from voice.settings import DEFAULT

    hardware = detect()
    installed = installed_models()
    profile = resolve(hardware, None, installed=installed)
    available, problem = check_model_available(profile)
    if not available:
        raise RuntimeError(problem)
    llm, handler, controller = make_llm_handler(profile, get_voice_tools(), modes=True, spoken=False,
                                                hardware=hardware, installed=installed)
    profile = fit_to_gpu(llm, profile, installed)
    if controller is not None:
        controller.rebase()

    def make_voice_loop(voice_handler: Any, events: Any) -> Any:  # noqa: ANN401
        from voice.pipeline import VoiceLoop

        return VoiceLoop(voice_handler, apply_to_voice_settings(profile, DEFAULT, hardware), events)

    gpu = hardware.gpu_name or "no GPU"
    return Assistant(llm=llm, handler=handler, controller=controller, profile=profile, hardware=hardware,
                     make_voice_loop=make_voice_loop,
                     describe={"model": profile.llm_model, "hardware": gpu})


class Session:
    def __init__(self, emit: Emit, build: Callable[[], Assistant] = build_assistant) -> None:
        self.emit = emit
        self._build = build
        self.assistant: Assistant | None = None
        self._lock = threading.Lock()
        self._busy = False             # a typed reply owns the model
        self._voice = None             # the running voice loop, which owns the model while it runs
        self._mic_starting = False     # a voice loop is being built (owns the model already)
        self._voice_thread: threading.Thread | None = None

    # ----------------------------------------------------------------- start

    def start(self) -> threading.Thread:
        """Load the model in the background; the page shows 'loading' until 'ready'."""
        thread = threading.Thread(target=self._load, name="halcyon-ui-load", daemon=True)
        thread.start()
        return thread

    def _load(self) -> None:
        self.emit({"type": "state", "state": "loading", "detail": "Loading the model"})
        try:
            self.assistant = self._build()
        except Exception as exc:  # noqa: BLE001 - shown in the window, not a crash
            self.emit({"type": "state", "state": "error", "detail": str(exc)})
            self.emit({"type": "error", "message": f"The assistant could not start: {exc}"})
            return
        self.emit({"type": "info", **self.assistant.describe, "mode": self._mode()})
        self.emit({"type": "state", "state": "ready"})

    # ------------------------------------------------------------------ text

    def send_text(self, text: str) -> bool:
        """
        Answer a typed message on a background thread. False (and nothing happens) when the text
        is empty, the model is not loaded yet, or a reply is still being written.
        """
        text = (text or "").strip()
        if not text or self.assistant is None:
            return False
        with self._lock:
            # While the microphone is on, the voice loop owns the model: one conversation at a time.
            if self._busy or self._voice is not None or self._mic_starting:
                return False
            self._busy = True
        threading.Thread(target=self._answer_text, args=(text,), name="halcyon-ui-text", daemon=True).start()
        return True

    def _answer_text(self, text: str) -> None:
        from voice.language import guess_language
        from voice.stt import Transcript

        try:
            self._typed(True)
            self.emit({"type": "user", "text": text, "via": "text"})
            self.emit({"type": "state", "state": "thinking"})
            self.emit({"type": "assistant_start"})
            transcript = Transcript(text=text, language=guess_language(text), language_probability=1.0,
                                    duration_ms=0, latency_ms=0)
            for delta in self.assistant.handler(transcript):
                if delta:
                    self.emit({"type": "delta", "text": delta})
            self.emit({"type": "assistant_done", "status": self._status()})
        except Exception as exc:  # noqa: BLE001
            self.emit({"type": "error", "message": str(exc)})
            self.emit({"type": "assistant_done", "status": ""})
        finally:
            with self._lock:
                self._busy = False
            self.emit({"type": "state", "state": "listening" if self._voice is not None else "ready"})

    # ----------------------------------------------------------------- voice

    def mic_on(self) -> bool:
        """Start listening (the user pressed the button). False if it is already on or not ready."""
        assistant = self.assistant
        if assistant is None or assistant.make_voice_loop is None:
            return False
        with self._lock:
            # Reserved before the loop is built, so a second request, or a typed reply, cannot
            # slip in between the check and the start (found in review).
            if self._busy or self._voice is not None or self._mic_starting:
                return False
            self._mic_starting = True
        from voice.pipeline import VoiceEvents

        def state(value: Any) -> None:  # noqa: ANN401
            self.emit({"type": "state", "state": VOICE_STATES.get(getattr(value, "name", str(value)), "ready")})

        def user(transcript: Any) -> None:  # noqa: ANN401
            self._typed(False)
            self.emit({"type": "user", "text": transcript.text, "via": "voice"})
            self.emit({"type": "assistant_start"})

        def speech_start() -> None:
            # The GPU idles down between turns; waking it while the user is still talking hides
            # the ~2 s it takes, as the terminal loop does (found in review).
            prewarm = getattr(assistant.llm, "prewarm", None)
            if prewarm is not None:
                prewarm()

        events = VoiceEvents(
            on_state=state,
            on_speech_start=speech_start,
            on_user=user,
            on_response_delta=lambda delta: self.emit({"type": "delta", "text": delta}),
            on_response_done=lambda _text: self.emit({"type": "assistant_done", "status": self._status()}),
            on_barge_in=lambda: self.emit({"type": "assistant_done", "status": "interrupted"}),
            on_error=lambda exc: self.emit({"type": "error", "message": str(exc)}),
        )
        try:
            loop = assistant.make_voice_loop(assistant.handler, events)
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._mic_starting = False
            self.emit({"type": "error", "message": f"The microphone could not start: {exc}"})
            self.emit({"type": "mic", "on": False})
            return False
        with self._lock:
            self._voice, self._mic_starting = loop, False
        self.emit({"type": "mic", "on": True})
        self.emit({"type": "state", "state": "loading", "detail": "Loading the speech models"})
        self._voice_thread = threading.Thread(target=self._run_voice, args=(loop,), name="halcyon-ui-voice",
                                              daemon=True)
        self._voice_thread.start()
        return True

    def _run_voice(self, loop: Any) -> None:  # noqa: ANN401
        try:
            loop.run()
        except Exception as exc:  # noqa: BLE001
            self.emit({"type": "error", "message": f"The microphone stopped: {exc}"})
        finally:
            try:
                loop.close()
            except Exception:  # noqa: BLE001
                pass
            with self._lock:
                if self._voice is loop:       # only the loop this worker ran
                    self._voice = None
            # Said whether it was turned off or stopped by an error, so the page never stays
            # in its microphone-on state with the message box off (found in review).
            self.emit({"type": "mic", "on": False})
            self.emit({"type": "state", "state": "ready"})

    def mic_off(self) -> bool:
        with self._lock:
            loop = self._voice
        if loop is None:
            return False
        loop.stop()
        return True

    def close(self) -> None:
        self.mic_off()

    # ---------------------------------------------------------------- helpers

    def _typed(self, typed: bool) -> None:
        """A typed turn gets the typed setup (more tool rounds); a spoken one the spoken setup."""
        from core.llm import SPOKEN_TOOL_ROUNDS, TYPED_TOOL_ROUNDS

        assistant = self.assistant
        if assistant is None:
            return
        if hasattr(assistant.llm, "max_tool_rounds"):
            assistant.llm.max_tool_rounds = TYPED_TOOL_ROUNDS if typed else SPOKEN_TOOL_ROUNDS
        if assistant.controller is not None:
            assistant.controller.spoken = not typed

    def _mode(self) -> str:
        controller = self.assistant.controller if self.assistant else None
        return controller.current.key if controller is not None else "general"

    def _status(self) -> str:
        controller = self.assistant.controller if self.assistant else None
        return controller.status() if controller is not None else ""
