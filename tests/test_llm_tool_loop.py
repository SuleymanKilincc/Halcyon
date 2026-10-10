"""
Tests for the conversation and tool-calling loop (core/llm.py).

Ollama is replaced by a fake client that returns scripted chunks. That lets
the tests check the things that actually broke in live use - tool results
reaching the model, the history being carried, text from two generation rounds
being joined with a space - without a model, a GPU or a network.
"""

from langchain_core.tools import tool

from core.llm import SpeechLLM, _to_ollama_tool
from core.profiles import PERFORMANCE


class FakeOllama:
    """Stands in for ollama.Client: returns one scripted response per chat() call."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def chat(self, **payload):
        # Snapshot the messages: the real loop keeps appending to the same
        # list, so storing it by reference would rewrite earlier requests.
        self.requests.append({**payload, "messages": list(payload["messages"])})
        return iter(self.responses.pop(0))


def text(content):
    return {"message": {"content": content}}


def tool_call(name, **arguments):
    return {"message": {"content": "", "tool_calls": [
        {"function": {"name": name, "arguments": arguments}}
    ]}}


@tool
def shout(word: str) -> str:
    """Return the word in capitals.

    A second paragraph that the model does not need to see.
    """
    return word.upper()


@tool
def explode() -> str:
    """Always fails."""
    raise RuntimeError("disk on fire")


def make_llm(responses, tools=()):
    llm = SpeechLLM(PERFORMANCE, base_url="http://test.invalid", tools=list(tools))
    llm._client = FakeOllama(responses)
    return llm


def test_plain_answer_is_streamed_and_remembered():
    llm = make_llm([[text("Merhaba "), text("efendim.")]])
    assert "".join(llm.stream("selam")) == "Merhaba efendim."
    assert [m["role"] for m in llm._history] == ["user", "assistant"]
    assert llm._history[-1]["content"] == "Merhaba efendim."


def test_history_is_sent_with_the_next_question():
    # This is the bug that made "show me" arrive with no antecedent: each turn
    # used to send only the system prompt and the newest sentence.
    llm = make_llm([[text("On bir klasör var.")], [text("On bir.")]])
    list(llm.stream("Klasörleri say"))
    list(llm.stream("Kaç taneydi?"))
    second_request = llm._client.requests[1]["messages"]
    contents = [m["content"] for m in second_request]
    assert "Klasörleri say" in contents
    assert "On bir klasör var." in contents


def test_tool_is_called_and_its_result_reaches_the_model():
    llm = make_llm(
        [[tool_call("shout", word="jarvis")], [text("Sonuç JARVIS.")]],
        tools=[shout],
    )
    answer = "".join(llm.stream("bağır"))
    assert answer == "Sonuç JARVIS."
    assert llm.last_tool_calls == ["shout"]
    second_request = llm._client.requests[1]["messages"]
    tool_messages = [m for m in second_request if m["role"] == "tool"]
    assert tool_messages[0]["content"] == "JARVIS"


def test_text_before_and_after_a_tool_call_is_joined_with_a_space():
    # Regression test. Each round is a separate generation, so the model
    # produced "...bakıyorum." and then "Efendim, ..." with nothing between
    # them. Joined raw, "bakıyorum.Efendim" has no space after the full stop,
    # the sentence splitter never fires, and nothing is spoken until the end.
    llm = make_llm(
        [[text("Bakıyorum."), tool_call("shout", word="x")], [text("Efendim, buldum.")]],
        tools=[shout],
    )
    assert "".join(llm.stream("bak")) == "Bakıyorum. Efendim, buldum."


def test_unknown_tool_is_reported_to_the_model_not_raised():
    llm = make_llm([[tool_call("no_such_tool")], [text("Yapamadım.")]], tools=[shout])
    assert "".join(llm.stream("dene")) == "Yapamadım."
    tool_message = next(m for m in llm._history if m["role"] == "tool")
    assert "no_such_tool" in tool_message["content"]


def test_a_failing_tool_does_not_crash_the_turn():
    llm = make_llm([[tool_call("explode")], [text("Bir hata oldu efendim.")]], tools=[explode])
    assert "".join(llm.stream("patlat")) == "Bir hata oldu efendim."
    tool_message = next(m for m in llm._history if m["role"] == "tool")
    assert "disk on fire" in tool_message["content"]


def test_history_is_trimmed_and_never_starts_with_a_tool_result():
    llm = make_llm([], tools=[shout])
    llm.history_turns = 2  # keep at most 4 messages
    llm._history = [
        {"role": "user", "content": "1"},
        {"role": "assistant", "content": "", "tool_calls": []},
        {"role": "tool", "name": "shout", "content": "X"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "2"},
        {"role": "assistant", "content": "a2"},
    ]
    llm._trim_history()
    assert len(llm._history) <= 4
    assert llm._history[0]["role"] == "user"


def test_tool_description_sent_to_the_model_is_only_the_first_paragraph():
    spec = _to_ollama_tool(shout)
    assert spec["function"]["name"] == "shout"
    assert spec["function"]["description"] == "Return the word in capitals."
