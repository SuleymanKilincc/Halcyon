"""
Tests for the repository itself, not for any module.

Three times in one session a scripted edit turned a backslash sequence into a control character:
a regex word boundary (\\b) became a backspace and stopped matching, and venv\\Scripts\\activate.bat
became venv\\Scripts<BEL>ctivate.bat, so the launcher could not find the virtual environment. The
edit tools reported success each time, and the diff looked right. This test makes the invariant
a check that runs on every push instead of something to remember.
"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BINARY = {".pdf", ".docx", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".wav", ".mp3", ".onnx", ".db", ".zip"}
# Tab, line feed and carriage return are text; every other C0 control character is a mistake.
CONTROL = {c for c in range(32) if c not in (9, 10, 13)}


def tracked_files():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        names = [line for line in out.splitlines() if line]
    except (OSError, subprocess.CalledProcessError):
        names = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts]
    return [ROOT / name for name in names]


def test_no_source_file_contains_a_control_character():
    found = []
    for path in tracked_files():
        if path.suffix.lower() in BINARY or not path.is_file():
            continue
        data = path.read_bytes()
        bad = sorted({b for b in data if b in CONTROL})
        if bad:
            found.append(f"{path.relative_to(ROOT)}: {', '.join(hex(b) for b in bad)}")
    assert not found, "control characters in:\n" + "\n".join(found)


def test_the_window_launcher_activates_the_virtual_environment():
    text = (ROOT / "start_halcyon_gui.bat").read_text(encoding="ascii")
    assert 'if exist "venv\\Scripts\\activate.bat" call "venv\\Scripts\\activate.bat"' in text
