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


# ------------------------------------------------ where things are on this computer

def test_the_environment_statement_gives_the_real_folders(tmp_path):
    from core.voice_tools import environment_statement

    (tmp_path / "Desktop").mkdir()
    (tmp_path / "Documents").mkdir()
    text = environment_statement(tmp_path)
    assert f"Desktop = {(tmp_path / 'Desktop').as_posix()}" in text
    assert f"Documents = {(tmp_path / 'Documents').as_posix()}" in text
    assert "Downloads" not in text            # absent folders are not invented
    assert "full paths" in text
    assert "never read out a full path" in text   # paths cannot be spoken


def test_a_desktop_redirected_to_a_cloud_folder_is_found(tmp_path):
    from core.voice_tools import environment_statement

    (tmp_path / "OneDrive" / "Desktop").mkdir(parents=True)
    assert (tmp_path / "OneDrive" / "Desktop").as_posix() in environment_statement(tmp_path)


def test_with_no_known_folders_the_statement_still_works(tmp_path):
    from core.voice_tools import environment_statement

    assert "none found" in environment_statement(tmp_path)
