"""
Which tools Jarvis may use when the instruction arrives by voice.

The full set in ``tools.py`` includes writing files, deleting files and running
shell commands. Those stay out of the voice path for now, and not because they
are hard to wire in — they are already wired for ``agent.py``. The reason is
that their safety depends on ``get_user_approval``, which falls back to
``input()`` on the terminal when no GUI callback is registered. In a voice
session nobody is watching the terminal: the prompt would block the loop in
silence, and a mis-heard sentence could reach a destructive tool with an
approval nobody consciously gave.

So the voice path gets the tools whose worst outcome is a wrong answer, and the
mutating ones are gated behind the approval/policy layer (Phase 3), where the
confirmation is spoken and has to be answered out loud.
"""

from __future__ import annotations

from typing import Any

# Read-only or otherwise non-destructive. A bad call here wastes a turn; it
# does not change anything on the machine.
VOICE_SAFE_TOOLS = (
    "list_directory",
    "read_file",
    "get_system_stats",
    "search_web",
    "fetch_webpage",
)

# Present in tools.py, deliberately withheld from voice until Phase 3.
VOICE_GATED_TOOLS = (
    "execute_terminal_command",
    "write_file",
    "append_to_file",
    "delete_file",
    "download_file",
    "extract_archive",
    "browse_website_interactive",
)


def get_voice_tools(include_gated: bool = False) -> list[Any]:
    """Return the tool objects Jarvis may call from a spoken instruction."""
    from tools import get_all_tools

    allowed = set(VOICE_SAFE_TOOLS)
    if include_gated:
        allowed |= set(VOICE_GATED_TOOLS)
    return [t for t in get_all_tools() if t.name in allowed]


def describe_voice_tools(include_gated: bool = False) -> str:
    names = [t.name for t in get_voice_tools(include_gated)]
    line = f"{len(names)} tools: {', '.join(names)}"
    if not include_gated:
        line += f"\n      (disabled until the confirmation layer exists: {', '.join(VOICE_GATED_TOOLS)})"
    return line


if __name__ == "__main__":
    print(describe_voice_tools())
