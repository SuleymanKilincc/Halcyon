"""
Tests for the typed mode of the voice CLI (voice/cli.py: run_typed).

Typing replaces speaking, so no microphone, speech model or speaker is
involved; the language model handler is a fake. What is tested is the loop
around it: what the handler is given, what is shown, and that the session
survives an empty line or an error.

The real handler yields raw text deltas (word pieces), not sentences, so the
fakes do too: joining them with anything but nothing splits words apart.
"""

from voice.cli import run_typed


class FakeLLM:
    def __init__(self, tools=()):
        self.last_tool_calls = list(tools)


def typed(lines, handler, llm=None):
    """Run the loop on scripted input; return (exit code, everything printed)."""
    remaining = iter(lines)
    printed = []

    def read_line(prompt):
        try:
            return next(remaining)
        except StopIteration:
            raise EOFError from None

    def write(*parts, end="\n", **kwargs):
        printed.append(" ".join(str(p) for p in parts) + end)

    clock = iter(range(0, 1000)).__next__  # 0, 1, 2 ... "seconds"
    code = run_typed(handler, llm, read_line, write, clock)
    return code, "".join(printed)


def test_the_typed_line_reaches_the_handler_with_its_language():
    seen = []

    def handler(transcript):
        seen.append((transcript.text, transcript.language))
        yield "Tamam."

    typed(["Masaüstümde neler var?", "What is on my desktop?"], handler)
    assert seen == [("Masaüstümde neler var?", "tr"), ("What is on my desktop?", "en")]


def test_deltas_are_printed_unchanged_so_words_are_not_split():
    # Word pieces as the model streams them: "Hal" + "cy" + "on".
    def handler(transcript):
        yield from ["The folder ", "Hal", "cy", "on", "_Demo", " has ", "three", " files."]

    _, printed = typed(["What is in the folder?"], handler)
    assert "The folder Halcyon_Demo has three files." in printed
    assert "Hal cy on" not in printed


def test_the_tools_used_and_the_time_to_first_text_are_shown():
    def handler(transcript):
        yield "There are three files."

    _, printed = typed(["What is in the folder?"], handler, FakeLLM(tools=["list_directory"]))
    assert "tools: list_directory" in printed
    assert "first text" in printed


def test_a_reply_without_tools_says_none():
    _, printed = typed(["hello"], lambda t: iter(["Hello, sir."]), FakeLLM())
    assert "tools: none" in printed


def test_leading_whitespace_before_the_reply_is_dropped():
    _, printed = typed(["hi"], lambda t: iter(["\n", "  ", "Hello."]))
    assert "Halcyon\033[0m: Hello." in printed


def test_empty_lines_are_skipped_and_exit_ends_the_session():
    calls = []

    def handler(transcript):
        calls.append(transcript.text)
        yield "ok"

    code, _ = typed(["", "   ", "exit", "never reached"], handler)
    assert code == 0 and calls == []


def test_the_end_of_input_ends_the_session_cleanly():
    code, _ = typed([], lambda t: iter(["unused"]))
    assert code == 0


def test_an_error_is_shown_and_the_session_continues():
    state = {"n": 0}

    def handler(transcript):
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("model server not reachable")
        yield "Back again."

    _, printed = typed(["first", "second"], handler)
    assert "model server not reachable" in printed and "Back again." in printed


def test_a_handler_that_says_nothing_is_reported():
    _, printed = typed(["hmm"], lambda t: iter([]))
    assert "(no reply)" in printed
    _, printed = typed(["hmm"], lambda t: iter(["  ", "\n"]))
    assert "(no reply)" in printed
