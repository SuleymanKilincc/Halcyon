"""
Manual check: print live hardware statistics through the get_system_stats tool.

    python -m scripts.manual.check_hardware

Not an automated test - it has nothing to assert, because the output depends
on this machine. Read it and judge. Automated tests live in tests/.
"""

import sys

from tools import get_system_stats


def main() -> None:
    # The report contains emoji. Windows consoles default to a legacy code
    # page (cp1254 for Turkish) that cannot encode them, and print() then
    # crashes after the tool has already succeeded.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    # get_system_stats is a LangChain tool, not a plain function: in
    # LangChain 1.x a tool is called through .invoke(), with its arguments
    # as a dict (empty here, because the tool takes none).
    print(get_system_stats.invoke({}))


if __name__ == "__main__":
    main()
