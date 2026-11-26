"""
Tests for keeping conversations on this computer: the store (ui/history.py), the session that
writes to it and switches between chats (ui/session.py), and the model picking an old chat up
again (SpeechLLM.load_history).

No window and no model: the store is a real SQLite file in a temporary folder, the assistant is
the fake of tests/test_ui_session.py with a model that records what it was given.
"""

import os
import threading
import time

import pytest

from core.profiles import PERFORMANCE
from test_ui_session import FakeController, FakeVoiceLoop, answer, failing_answer, slow_answer, wait_for
from ui.history import History, default_path, title_from
from ui.session import Assistant, Session


@pytest.fixture
def store(tmp_path):
    history = History(tmp_path / "history.db", clock=iter(range(1000, 100000)).__next__)
    yield history
    history.close()


# ------------------------------------------------------------------- the store

def test_a_chat_keeps_its_messages_in_order(store):
    chat = store.create("What is a dict in Python?")
    store.add(chat, "user", "What is a dict in Python?")
    store.add(chat, "assistant", "A mapping of keys to values.")
    store.add(chat, "user", "can I loop over it", via="voice")
    assert store.messages(chat) == [
        {"role": "user", "text": "What is a dict in Python?", "via": "text", "status": ""},
        {"role": "assistant", "text": "A mapping of keys to values.", "via": "text", "status": ""},
        {"role": "user", "text": "can I loop over it", "via": "voice", "status": ""},
    ]
    assert store.chats()[0]["title"] == "What is a dict in Python?"


def test_chats_are_listed_pinned_first_then_most_recent(store):
    old, middle, new = store.create("old"), store.create("middle"), store.create("new")
    store.add(middle, "user", "touched last")
    store.pin(old, True)
    assert [c["title"] for c in store.chats()] == ["old", "middle", "new"]
    assert store.chats()[0]["pinned"] is True


def test_a_long_first_message_becomes_a_short_title_cut_at_a_word():
    title = title_from("Bana Python ile asal sayıları bulan, hızlı ve okunabilir bir fonksiyon yazar mısın lütfen?")
    assert len(title) <= 49 and title.endswith("…") and not title[:-1].endswith(" ")
    assert title_from("  two\nlines  ") == "two lines"


def test_rename_and_its_limits(store):
    chat = store.create("x")
    assert store.rename(chat, "  Asal   sayılar  ")
    assert store.chats()[0]["title"] == "Asal sayılar"
    assert not store.rename(chat, "   ")                 # an empty name is refused, the old one stays
    assert store.chats()[0]["title"] == "Asal sayılar"
    assert not store.rename(999, "nothing there")


def test_deleting_a_chat_deletes_its_messages(store):
    chat = store.create("x")
    store.add(chat, "user", "hello")
    assert store.delete(chat)
    assert store.chats() == [] and store.messages(chat) == []
    assert not store.delete(chat)
    assert not store.add(chat, "assistant", "a reply that arrives after the delete")


def test_a_deleted_chat_cannot_be_read_back_out_of_the_file(tmp_path):
    """Deleting means deleting: SQLite would otherwise leave the text in free pages of the file."""
    path = tmp_path / "history.db"
    store = History(path)
    chat = store.create("private")
    store.add(chat, "user", "my-secret-marker-7f3a " * 50)
    store.delete(chat)
    store.close()
    assert b"my-secret-marker-7f3a" not in path.read_bytes()


def test_the_file_lives_in_the_users_own_data_folder():
    assert default_path({"HALCYON_DATA": "D:/data"}).as_posix() == "D:/data/history.db"
    import sys

    if sys.platform == "win32":
        assert default_path({"LOCALAPPDATA": "C:/Users/u/AppData/Local"}).as_posix() == \
            "C:/Users/u/AppData/Local/Halcyon/history.db"


# ------------------------------------------------------------------ the session

class RecordingLLM:
    max_tool_rounds = 4

    def __init__(self):
        self.loaded = None
        self.resets = 0

    def load_history(self, messages):
        self.loaded = messages

    def reset(self):
        self.resets += 1


class ForgettingController(FakeController):
    def __init__(self):
        super().__init__()
        self.forgotten = 0

    def forget(self):
        self.forgotten += 1


def make(store, handler=answer, voice_loop=None, build_gate=None):
    events = []
    assistant = Assistant(llm=RecordingLLM(), handler=handler, controller=ForgettingController(),
                          make_voice_loop=voice_loop, describe={"model": "fake:1b", "hardware": "fake GPU"})

    def build():
        if build_gate is not None:
            build_gate.wait(2)
        return assistant

    session = Session(events.append, build=build, history=store)
    thread = session.start()
    if build_gate is None:
        thread.join(2)
    return session, events, assistant


def exchange(session, events, text="hi"):
    done = sum(1 for e in events if e["type"] == "assistant_done")
    assert session.send_text(text)
    wait_for(events, "assistant_done", count=done + 1)
    deadline = time.time() + 2
    while session._busy and time.time() < deadline:
        time.sleep(0.01)


def test_a_typed_exchange_is_saved_and_the_list_follows(store):
    session, events, _ = make(store)
    assert events[1] == {"type": "chats", "chats": []}      # the list is there before the model is
    exchange(session, events, "What is a dict?")
    chat = session.chat_id
    assert {"type": "chat", "id": chat} in events
    assert store.messages(chat) == [
        {"role": "user", "text": "What is a dict?", "via": "text", "status": ""},
        {"role": "assistant", "text": "Hello there.", "via": "text", "status": ""},
    ]
    assert events[-1]["type"] == "state" or any(e["type"] == "chats" and e["chats"] for e in events)
    exchange(session, events, "and a list?")
    assert len(store.chats()) == 1 and len(store.messages(chat)) == 4


def test_a_spoken_exchange_is_saved_as_spoken(store):
    session, events, _ = make(store, voice_loop=lambda h, e: FakeVoiceLoop(h, e))
    session.mic_on()
    wait_for(events, "assistant_done")
    session.mic_off()
    wait_for(events, "mic", count=2)
    assert [m["via"] for m in store.messages(session.chat_id)] == ["voice", "voice"]


def test_an_error_is_shown_but_not_saved_as_a_reply(store):
    session, events, _ = make(store, handler=failing_answer)
    exchange(session, events)
    texts = [m["text"] for m in store.messages(session.chat_id)]
    assert texts == ["hi", "Half"]                       # what was written before it failed is kept
    assert not any("model went away" in t for t in texts)


def test_reopening_a_chat_shows_it_and_gives_the_model_its_history(store):
    session, events, assistant = make(store)
    exchange(session, events, "first chat")
    first = session.chat_id
    assert session.new_chat()
    exchange(session, events, "second chat")
    assert session.chat_id != first and len(store.chats()) == 2

    assert session.open_chat(first)
    shown = [e for e in events if e["type"] == "conversation"][-1]
    assert shown["id"] == first and [m["text"] for m in shown["messages"]] == ["first chat", "Hello there."]
    assert [m["text"] for m in assistant.llm.loaded] == ["first chat", "Hello there."]
    assert assistant.controller.forgotten == 2          # a waiting offer belonged to the other chat
    exchange(session, events, "carry on")
    assert len(store.messages(first)) == 4


def test_a_new_chat_starts_the_model_afresh(store):
    session, events, assistant = make(store)
    exchange(session, events)
    assert session.new_chat()
    assert assistant.llm.resets == 1 and session.chat_id is None
    assert [e for e in events if e["type"] == "conversation"][-1] == {"type": "conversation", "id": None,
                                                                       "messages": []}


def test_no_switching_while_a_reply_is_written_or_the_microphone_is_on(store):
    session, events, _ = make(store, handler=slow_answer, voice_loop=lambda h, e: FakeVoiceLoop(h, e))
    exchange(session, events)
    first = session.chat_id
    session.new_chat()
    assert session.send_text("busy now")
    assert not session.open_chat(first) and not session.new_chat()
    wait_for(events, "assistant_done", count=2)
    time.sleep(0.05)
    assert session.mic_on()
    assert not session.open_chat(first) and not session.new_chat()
    session.mic_off()


def test_the_chat_on_screen_can_be_deleted_and_the_screen_is_cleared(store):
    session, events, assistant = make(store)
    exchange(session, events)
    chat = session.chat_id
    assert session.delete_chat(chat)
    assert store.chats() == [] and session.chat_id is None and assistant.llm.resets == 1
    assert events[-2] == {"type": "conversation", "id": None, "messages": []}
    assert events[-1] == {"type": "chats", "chats": []}


def test_the_chat_being_written_cannot_be_deleted_but_another_can(store):
    session, events, _ = make(store, handler=slow_answer)
    exchange(session, events, "older")
    older = session.chat_id
    session.new_chat()
    assert session.send_text("now")
    deadline = time.time() + 2
    while session.chat_id in (None, older) and time.time() < deadline:
        time.sleep(0.01)
    assert not session.delete_chat(session.chat_id)
    assert session.delete_chat(older)
    wait_for(events, "assistant_done", count=2)


def test_rename_and_pin_reach_the_list(store):
    session, events, _ = make(store)
    exchange(session, events)
    chat = session.chat_id
    assert session.rename_chat(chat, "Selamlaşma")
    assert session.pin_chat(chat, True)
    assert events[-1] == {"type": "chats", "chats": [
        {"id": chat, "title": "Selamlaşma", "pinned": True, "updated": store.chats()[0]["updated"]}]}


def test_a_chat_opened_while_the_model_loads_is_given_to_it_once_loaded(store):
    chat = store.create("earlier")
    store.add(chat, "user", "earlier")
    store.add(chat, "assistant", "reply")
    gate = threading.Event()
    session, events, assistant = make(store, build_gate=gate)
    time.sleep(0.05)
    assert session.open_chat(chat)                       # readable before the model is there
    assert assistant.llm.loaded is None
    gate.set()
    wait_for(events, "info")
    assert [m["text"] for m in assistant.llm.loaded] == ["earlier", "reply"]


def test_a_store_that_fails_does_not_stop_the_conversation(store):
    session, events, _ = make(store)

    def broken(*args, **kwargs):
        raise OSError("disk full")

    store.add = broken
    exchange(session, events)
    assert any(e["type"] == "error" and "disk full" in e["message"] for e in events)
    assert session.send_text("still talking")


def test_without_a_store_nothing_is_kept_and_nothing_can_be_opened():
    events = []
    assistant = Assistant(llm=RecordingLLM(), handler=answer, controller=ForgettingController())
    session = Session(events.append, build=lambda: assistant)
    session.start().join(2)
    assert not any(e["type"] == "chats" for e in events)
    assert session.chats() == [] and not session.open_chat(1) and not session.delete_chat(1)
    assert any(e["type"] == "info" and e["history"] is False for e in events)


# ------------------------------------------------------------------ the model

def test_the_model_carries_on_a_reopened_chat():
    from test_llm_tool_loop import make_llm, text

    llm = make_llm([[text("Yes, with .items().")]])
    llm.load_history([
        {"role": "user", "text": "What is a dict?"},
        {"role": "assistant", "text": "A mapping."},
        {"role": "assistant", "text": "   "},            # nothing to say: left out
        {"role": "error", "text": "model went away"},      # not part of the conversation
    ])
    "".join(llm.stream("Can I loop over it?"))
    sent = [(m["role"], m["content"]) for m in llm._client.requests[0]["messages"][1:]]
    assert sent == [("user", "What is a dict?"), ("assistant", "A mapping."), ("user", "Can I loop over it?")]


def test_a_long_reopened_chat_is_cut_to_the_usual_length():
    from core.llm import SpeechLLM

    llm = SpeechLLM(PERFORMANCE, base_url="http://test.invalid", history_turns=2)
    turns = []
    for i in range(10):
        turns += [{"role": "user", "text": f"q{i}"}, {"role": "assistant", "text": f"a{i}"}]
    llm.load_history(turns)
    assert [m["content"] for m in llm._history] == ["q8", "a8", "q9", "a9"]


# ------------------------------------------------------------- found in Qodo's review of #6

def test_a_reply_cut_short_by_an_error_is_marked_and_not_given_back_to_the_model(store):
    session, events, _ = make(store, handler=failing_answer)
    exchange(session, events)
    assert store.messages(session.chat_id)[-1] == {"role": "assistant", "text": "Half", "via": "text",
                                                   "status": "error"}
    from test_llm_tool_loop import make_llm

    llm = make_llm([])
    llm.load_history(store.messages(session.chat_id))
    assert [m["content"] for m in llm._history] == ["hi"]


def test_an_error_outside_a_reply_marks_nothing(store):
    session, events, _ = make(store)
    session.emit({"type": "error", "message": "The microphone could not start"})
    exchange(session, events)
    assert store.messages(session.chat_id)[-1]["status"] == ""


@pytest.mark.skipif(os.name != "posix", reason="Windows keeps other users out with the profile's access list")
def test_saved_chats_are_readable_by_their_owner_only(tmp_path):
    old = os.umask(0o022)
    try:
        History(tmp_path / "data" / "history.db").close()
    finally:
        os.umask(old)
    assert (tmp_path / "data").stat().st_mode & 0o777 == 0o700
    assert (tmp_path / "data" / "history.db").stat().st_mode & 0o777 == 0o600


def test_a_history_that_cannot_open_leaves_the_window_working(tmp_path, monkeypatch):
    from ui.app import open_history

    blocker = tmp_path / "not-a-folder"
    blocker.write_text("x")
    monkeypatch.setenv("HALCYON_DATA", str(blocker))
    history, problem = open_history()
    assert history is None and "cannot be saved" in problem

    damaged = tmp_path / "damaged"
    damaged.mkdir()
    (damaged / "history.db").write_bytes(b"this is not a database" * 100)
    monkeypatch.setenv("HALCYON_DATA", str(damaged))
    history, problem = open_history()
    assert history is None and problem


def test_the_window_keeps_its_page_storage_and_lets_text_be_selected(tmp_path, monkeypatch):
    """Found in review of #6: pywebview's private mode forgot the TR/EN choice on every restart."""
    import sys
    import types

    calls = {}
    fake = types.ModuleType("webview")
    fake.create_window = lambda *a, **k: calls.setdefault("window", k) and object()
    fake.start = lambda **k: calls.setdefault("start", k)
    monkeypatch.setitem(sys.modules, "webview", fake)
    monkeypatch.setenv("HALCYON_DATA", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["ui", "--demo"])
    from ui.app import main

    assert main() == 0
    assert calls["window"]["text_select"] is True
    assert calls["start"]["private_mode"] is False
    assert calls["start"]["storage_path"].startswith(str(tmp_path))
