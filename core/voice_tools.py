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


# How each tool is described to the model when it explains what it can and
# cannot do. Generated into the system prompt from the tools actually enabled,
# so the description cannot drift from the truth when a tool is switched on.
ABILITY = {
    "list_directory": "list what is inside a folder",
    "read_file": "read a text file",
    "get_system_stats": "report hardware statistics such as temperatures, load, memory and battery",
    "search_web": "search the web",
    "fetch_webpage": "read a web page",
    "execute_terminal_command": "run commands or programs",
    "write_file": "create or overwrite files",
    "append_to_file": "edit files",
    "delete_file": "delete files",
    "download_file": "download files",
    "extract_archive": "extract archives",
    "browse_website_interactive": "control a web browser",
}


def capability_statement(tools: list[Any]) -> str:
    """
    The part of the system prompt that tells the model what it can and cannot do.

    Built from the enabled tools rather than written by hand: in a live session
    the model said "let me attempt" creating a folder, called an unrelated web
    search, then said it could not - it had never been told which actions were
    switched off, or why.
    """
    enabled = [t.name for t in tools]
    can = [ABILITY[name] for name in enabled if name in ABILITY]
    cannot = [ABILITY[name] for name in VOICE_GATED_TOOLS if name not in enabled]
    if "write_file" not in enabled:
        cannot.append("create folders")

    lines = []
    if can:
        lines.append("What you can do, using your tools: " + "; ".join(can) + ". "
                     "Call a tool only when the request needs it.")
    else:
        lines.append("You have no tools in this conversation.")
    if cannot:
        lines.append("What you cannot do yet: " + "; ".join(cannot) + ". These are switched off "
                     "until a spoken confirmation step exists. When asked for one, say in one "
                     "sentence that you cannot do it yet, and offer the closest thing you can do.")
    return "\n".join(lines)


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
