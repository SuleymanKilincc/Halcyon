"""
Tests for the capability statement in the system prompt (core/voice_tools.py).

The statement is generated from the enabled tools, so these tests check that
what Halcyon is told about itself follows the tools - including the day a
currently disabled tool is switched on.
"""

from core.voice_tools import VOICE_GATED_TOOLS, VOICE_SAFE_TOOLS, capability_statement


class Tool:
    def __init__(self, name):
        self.name = name


def statement(names):
    return capability_statement([Tool(n) for n in names])


def test_enabled_tools_are_listed_as_abilities():
    text = statement(VOICE_SAFE_TOOLS)
    can = text.split("What you cannot do")[0]
    assert "list what is inside a folder" in can
    assert "search the web" in can


def test_disabled_tools_are_listed_as_things_it_cannot_do():
    text = statement(VOICE_SAFE_TOOLS)
    cannot = text.split("What you cannot do")[1]
    for ability in ("delete files", "run commands or programs", "download files", "create folders"):
        assert ability in cannot


def test_the_reason_and_the_expected_reply_are_stated():
    text = statement(VOICE_SAFE_TOOLS)
    assert "spoken confirmation" in text
    assert "say in one sentence that you cannot do it yet" in text


def test_enabling_a_tool_moves_it_from_cannot_to_can():
    # The day writing files is switched on, Halcyon must stop saying it cannot.
    text = statement([*VOICE_SAFE_TOOLS, "write_file"])
    can, cannot = text.split("What you cannot do")
    assert "create or overwrite files" in can
    assert "create or overwrite files" not in cannot
    assert "create folders" not in cannot


def test_every_tool_has_a_description():
    from core.voice_tools import ABILITY

    for name in (*VOICE_SAFE_TOOLS, *VOICE_GATED_TOOLS):
        assert name in ABILITY, name


def test_no_tools_at_all():
    assert "You have no tools" in statement([])
