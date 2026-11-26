"""
Tests for what the window talks to (ui/session.py) and the bridge the page calls (ui/app.py).

No window, no model, no microphone: the assistant is a fake that answers with fixed text, and
the voice loop is a fake that plays a scripted turn. What is checked is what the page sees -
the events, in order - and the rules that keep one conversation at a time.
"""

import threading
import time

from ui.app import Bridge
from ui.session import Assistant, Session


class FakeLLM:
    max_tool_rounds = 4


class FakeController:
    def __init__(self):
        self.spoken = True
        self.current = type("Mode", (), {"key": "general"})()

    def status(self):
        return "mode: general | request: chat tier 0"

    def set_spoken(self, spoken):
        self.spoken = spoken


def answer(transcript):
    yield "Hello "
    yield "there."


def slow_answer(transcript):
    time.sleep(0.3)
    yield "done"


def failing_answer(transcript):
    yield "Half"
    raise RuntimeError("model went away")


def make(handler=answer, voice_loop=None):
    events = []
    controller = FakeController()
    assistant = Assistant(llm=FakeLLM(), handler=handler, controller=controller,
                          make_voice_loop=voice_loop, describe={"model": "fake:1b", "hardware": "fake GPU"})
    session = Session(events.append, build=lambda: assistant)
    session.start().join(2)
    return session, events, assistant


def wait_for(events, kind, count=1, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if sum(1 for e in events if e["type"] == kind) >= count:
            return
        time.sleep(0.01)
    raise AssertionError(f"no {kind} event in {events}")


# ------------------------------------------------------------------- loading

def test_loading_is_shown_and_then_ready_with_what_was_loaded():
    _, events, _ = make()
    assert events[0] == {"type": "state", "state": "loading", "detail": "Loading the model"}
    assert {"type": "info", "model": "fake:1b", "hardware": "fake GPU", "mode": "general",
            "history": False} in events
    assert events[-1] == {"type": "state", "state": "ready"}


def test_a_model_that_cannot_load_is_shown_as_an_error_not_a_crash():
    events = []

    def broken():
        raise RuntimeError("Ollama is not running")

    Session(events.append, build=broken).start().join(2)
    assert {"type": "state", "state": "error", "detail": "Ollama is not running"} in events
    assert any(e["type"] == "error" and "Ollama is not running" in e["message"] for e in events)


# ---------------------------------------------------------------------- text

def test_a_typed_message_comes_back_as_events_in_order():
    session, events, _ = make()
    start = len(events)
    assert session.send_text("  hi  ")
    wait_for(events, "assistant_done")
    wait_for(events, "state", count=3)
    kinds = [(e["type"], e.get("state") or e.get("text") or e.get("status")) for e in events[start:]]
    assert kinds == [("user", "hi"), ("state", "thinking"), ("assistant_start", None), ("delta", "Hello "),
                     ("delta", "there."), ("assistant_done", "mode: general | request: chat tier 0"),
                     ("state", "ready")]


def test_a_typed_turn_gets_the_typed_setup():
    from core.llm import TYPED_TOOL_ROUNDS

    session, events, assistant = make()
    session.send_text("hi")
    wait_for(events, "assistant_done")
    assert assistant.llm.max_tool_rounds == TYPED_TOOL_ROUNDS
    assert assistant.controller.spoken is False


def test_one_reply_at_a_time():
    session, events, _ = make(handler=slow_answer)
    assert session.send_text("first")
    assert not session.send_text("second")              # still writing the first
    wait_for(events, "assistant_done")
    time.sleep(0.05)
    assert session.send_text("third")


def test_nothing_is_sent_before_the_model_is_loaded_or_when_empty():
    events = []
    gate = threading.Event()
    session = Session(events.append, build=lambda: (gate.wait(2), Assistant(llm=FakeLLM(), handler=answer))[1])
    session.start()
    assert not session.send_text("too early")
    gate.set()
    time.sleep(0.1)
    assert not session.send_text("   ")


def test_a_reply_that_fails_half_way_says_so_and_the_session_carries_on():
    session, events, _ = make(handler=failing_answer)
    session.send_text("hi")
    wait_for(events, "assistant_done")
    assert any(e["type"] == "error" and "model went away" in e["message"] for e in events)
    time.sleep(0.05)
    assert session.send_text("again")


# --------------------------------------------------------------------- voice

class FakeVoiceLoop:
    """Plays one spoken turn through the events, then waits until stopped."""

    def __init__(self, handler, events):
        self.handler, self.events = handler, events
        self.stopped = threading.Event()
        self.closed = False

    def run(self):
        from voice.pipeline import State
        from voice.stt import Transcript

        self.events.emit("on_state", State.LISTENING)
        transcript = Transcript(text="what time is it", language="en", language_probability=1.0,
                                duration_ms=0, latency_ms=0)
        self.events.emit("on_user", transcript)
        self.events.emit("on_state", State.RESPONDING)
        for delta in self.handler(transcript):
            self.events.emit("on_response_delta", delta)
        self.events.emit("on_response_done", "Hello there.")
        self.events.emit("on_state", State.LISTENING)
        self.stopped.wait(3)

    def stop(self):
        self.stopped.set()

    def close(self):
        self.closed = True


def test_the_microphone_turns_a_spoken_turn_into_the_same_events():
    loops = []

    def voice_loop(handler, events):
        loops.append(FakeVoiceLoop(handler, events))
        return loops[-1]

    session, events, assistant = make(voice_loop=voice_loop)
    start = len(events)
    assert session.mic_on()
    wait_for(events, "assistant_done")
    seen = [(e["type"], e.get("state") or e.get("text") or e.get("via")) for e in events[start:]]
    assert ("user", "what time is it") in seen
    assert ("state", "listening") in seen and ("state", "thinking") in seen
    assert [e["text"] for e in events[start:] if e["type"] == "delta"] == ["Hello ", "there."]
    assert assistant.controller.spoken is True                    # a spoken turn gets the spoken setup
    assert not session.send_text("typed while listening")         # one conversation at a time
    assert not session.mic_on()                                    # already on
    assert session.mic_off()
    wait_for(events, "state", count=len([e for e in events if e["type"] == "state"]) + 1)
    assert loops[0].closed


def test_the_microphone_is_never_opened_by_the_session_itself():
    opened = []
    session, events, _ = make(voice_loop=lambda h, e: opened.append(1) or FakeVoiceLoop(h, e))
    session.send_text("hi")
    wait_for(events, "assistant_done")
    assert opened == []


# --------------------------------------------------------------------- bridge

class FakeWindow:
    def __init__(self):
        self.scripts = []

    def evaluate_js(self, script):
        self.scripts.append(script)


def test_events_before_the_page_is_ready_are_kept_and_sent_in_order():
    bridge = Bridge()
    bridge._attach(FakeWindow(), None)
    bridge.emit({"type": "state", "state": "loading"})
    bridge.emit({"type": "state", "state": "ready"})
    assert bridge._window.scripts == []
    bridge.ready()
    assert len(bridge._window.scripts) == 2
    assert '"loading"' in bridge._window.scripts[0] and '"ready"' in bridge._window.scripts[1]
    bridge.emit({"type": "delta", "text": "x"})
    assert '"delta"' in bridge._window.scripts[2]


def test_text_from_the_model_cannot_break_out_of_the_script_it_is_sent_in():
    bridge = Bridge()
    bridge._attach(FakeWindow(), None)
    bridge.ready()
    bridge.emit({"type": "delta", "text": '"); alert(1); ("</script>'})
    script = bridge._window.scripts[0]
    assert script.startswith("window.halcyon && window.halcyon.receive(") and script.endswith(")")
    assert '\\"); alert(1); (\\"' in script                   # quotes escaped by JSON


def test_the_page_cannot_act_before_there_is_a_session():
    bridge = Bridge()
    assert bridge.send("hi") is False and bridge.mic(True) is False


def test_the_page_sees_only_the_calls_it_needs():
    """pywebview exposes every public attribute to the page and walks into it."""
    public = {name for name in vars(Bridge()) if not name.startswith("_")} |              {name for name in dir(Bridge) if not name.startswith("_")}
    assert public == {"ready", "send", "mic", "emit", "chats", "new_chat", "open_chat", "rename_chat",
                      "pin_chat", "delete_chat", "settings"}


def test_the_window_opens_the_page_by_a_plain_file_address():
    """WebView2 reads a query string as part of the file name: index.html?demo=1 was "File not found"."""
    from ui.app import page_url

    url = page_url()
    assert url.startswith("file:") and url.endswith("/index.html") and "?" not in url


def test_the_page_gets_its_language_and_demo_setting_from_the_bridge():
    assert Bridge(language="tr", demo=True).settings() == {"language": "tr", "demo": True}
    assert Bridge().settings() == {"language": "en", "demo": False}


# ------------------------------------------------------------------ found in Qodo's review of #5

def test_the_microphone_cannot_start_while_a_typed_reply_is_written():
    loops = []
    session, events, _ = make(handler=slow_answer, voice_loop=lambda h, e: loops.append(1) or FakeVoiceLoop(h, e))
    assert session.send_text("hi")
    assert not session.mic_on()
    wait_for(events, "assistant_done")
    assert loops == []


def test_two_microphone_requests_at_once_start_one_loop():
    built = []
    gate = threading.Event()

    def voice_loop(handler, events):
        gate.wait(1)                          # hold the first start open while the second arrives
        built.append(FakeVoiceLoop(handler, events))
        return built[-1]

    session, events, _ = make(voice_loop=voice_loop)
    results = []
    threads = [threading.Thread(target=lambda: results.append(session.mic_on())) for _ in range(2)]
    for thread in threads:
        thread.start()
    time.sleep(0.1)
    gate.set()
    for thread in threads:
        thread.join(2)
    assert sorted(results) == [False, True] and len(built) == 1
    session.mic_off()


def test_the_page_hears_the_microphone_go_on_and_off_even_after_an_error():
    class BrokenLoop(FakeVoiceLoop):
        def run(self):
            raise RuntimeError("no input device")

    session, events, _ = make(voice_loop=lambda h, e: BrokenLoop(h, e))
    assert session.mic_on()
    wait_for(events, "mic", count=2)
    mics = [e["on"] for e in events if e["type"] == "mic"]
    assert mics == [True, False]
    assert any("no input device" in e.get("message", "") for e in events)
    time.sleep(0.05)
    assert session.send_text("typing works again")


def test_speech_starting_wakes_the_gpu_as_the_terminal_loop_does():
    woken = []

    class SpeakingLoop(FakeVoiceLoop):
        def run(self):
            self.events.emit("on_speech_start")
            self.stopped.wait(1)

    session, events, assistant = make(voice_loop=lambda h, e: SpeakingLoop(h, e))
    assistant.llm.prewarm = lambda: woken.append(1)
    session.mic_on()
    time.sleep(0.1)
    session.mic_off()
    assert woken == [1]


def test_an_event_emitted_while_the_page_catches_up_comes_after_the_ones_it_was_waiting_for():
    class SlowWindow(FakeWindow):
        def evaluate_js(self, script):
            super().evaluate_js(script)
            if len(self.scripts) == 1:
                late = threading.Thread(target=bridge.emit, args=({"type": "state", "state": "thinking"},))
                late.start()
                late.join(0.2)              # blocked until the backlog is out

    bridge = Bridge()
    bridge._attach(SlowWindow(), None)
    bridge.emit({"type": "state", "state": "loading"})
    bridge.emit({"type": "state", "state": "ready"})
    bridge.ready()
    time.sleep(0.3)
    order = [s.split('"state": "')[1].split('"')[0] for s in bridge._window.scripts]
    assert order == ["loading", "ready", "thinking"]


def test_the_page_is_told_which_whisper_the_microphone_got():
    def voice_loop(handler, events):
        assistant.describe["speech"] = "small"
        return FakeVoiceLoop(handler, events)

    session, events, assistant = make(voice_loop=voice_loop)
    assert session.mic_on()
    wait_for(events, "info", count=2)
    assert [e for e in events if e["type"] == "info"][-1]["speech"] == "small"
    session.mic_off()
