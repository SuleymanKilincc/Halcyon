"""
Reading and searching files for the assistant: the logic behind its read-only file tools.

Measured before this module existed (bench/task_eval.py, docs/TOOLS.md), the old tools failed
the same tasks for every model, because the tools could not do them:

* `read_file` returned a whole file and the tool loop kept its first 4000 characters, so the
  end of a long log was out of reach (the last error of a 3000-line log, at character 164,000);
* a PDF or a Word file came back as raw bytes;
* a definition a few folders down could only be found by opening folders one by one, and the
  loop ran out of rounds first;
* a name given without its extension ("README" for README.md) was simply "not found".

So the tools get, from here:

* **a window of a file that always fits**, with line numbers: from any line, or the last lines
  (`start_line=-50`) for logs; PDF and Word documents are read as their text;
* **a search** for some text in a file or in every file under a folder, so "where is X
  defined?" and "what was the last error?" take one call;
* **a listing several levels deep**, so the layout of a project takes one call too;
* **forgiving names**: a name that matches exactly one file in its folder (wrong case, no
  extension) is used, and one that matches nothing comes back with what the folder does
  contain, so the next call can be right without a separate listing.

Everything here is read-only. Standard library only; pypdf and python-docx are imported when
such a document is actually read.
"""

from __future__ import annotations

import os
import re
import time
from collections import deque
from collections.abc import Iterator
from pathlib import Path

# One tool result must fit the tool loop's cap (4000 characters in core/llm.py) with room for
# the header and the footer, or the loop would cut the window it was given.
WINDOW_CHARS = 3500
LINE_CHARS = 300                # one line longer than this is cut (minified code, long log lines)
SEARCH_LINE_CHARS = 200
SEARCH_MAX_SHOWN = 30
SEARCH_MAX_FILES = 4000
SEARCH_MAX_SECONDS = 5.0
SEARCH_MAX_FILE_BYTES = 5 * 1024 * 1024       # per file when searching a folder
MAX_TEXT_BYTES = 50 * 1024 * 1024             # a single file read or searched on its own
MAX_DOCUMENTS_IN_SEARCH = 30
# A PDF or Word file is parsed whole before a window of it can be shown, so a large one is refused
# before parsing instead of stalling the tool (found in review).
MAX_DOCUMENT_BYTES = 30 * 1024 * 1024
SEARCH_MAX_FILES_COUNTED = 1000   # files whose extra matches are counted by name in a folder search
MAX_PDF_PAGES = 300
TREE_MAX_DEPTH = 4
FOLDER_PREVIEW = 30             # names shown when a path is wrong, so the next call can be right

# Folders that are never what the user means and can hold hundreds of thousands of files.
SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".tox", ".idea", ".vscode", "site-packages", ".cache",
})
DOCUMENT_SUFFIXES = frozenset({".pdf", ".docx"})
# What matters in a log is the latest; read from the start, the 9B model invented the "last
# error" of a log whose first page had none (measured). A log is shown from its end by default.
LOG_SUFFIXES = frozenset({".log", ".out", ".err"})
BINARY_SUFFIXES = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".tif", ".tiff", ".psd",
    ".mp3", ".wav", ".ogg", ".flac", ".m4a", ".mp4", ".mkv", ".avi", ".mov", ".webm",
    ".zip", ".7z", ".rar", ".tar", ".gz", ".bz2", ".xz", ".iso", ".msi", ".exe", ".dll", ".so",
    ".dylib", ".bin", ".pyc", ".pyd", ".o", ".obj", ".class", ".jar", ".db", ".sqlite",
    ".sqlite3", ".gguf", ".onnx", ".pt", ".pth", ".safetensors", ".npy", ".npz", ".pkl",
    ".doc", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ttf", ".otf", ".woff", ".woff2",
})


# ---------------------------------------------------------------------------- names


def resolve(path_text: str, base: Path, *, want: str = "any") -> tuple[Path | None, str]:
    """
    The file or folder a tool argument names, as (path, note); (None, message) if nothing fits.

    `base` is where a relative path points (the assistant's workspace folder). `want` is
    "file", "dir" or "any". The note is empty unless the name had to be corrected, and then
    says so, so the model never reports a file it did not ask for as if it had.
    """
    raw = (path_text or "").strip().strip('"').strip("'").strip()
    if not raw:
        return None, "No path was given."
    path = Path(os.path.expanduser(raw))
    if not path.is_absolute():
        path = base / path
    if path.exists():
        return _check_kind(path, want)

    parent = path.parent
    if parent.is_dir():
        found = [p for p in _near_names(parent, path.name) if _kind_ok(p, want)]
        if len(found) == 1:
            match = found[0]
            return match, (f"(There is no '{path.name}' in {parent.as_posix()}; this is {match.name}, "
                           f"the only name there that matches.)")
        if found:
            names = ", ".join(p.name for p in found[:10])
            return None, f"There is no '{path.name}' in {parent.as_posix()}. Names that match: {names}."
        return None, f"There is no '{path.name}' in {parent.as_posix()}. {folder_summary(parent)}"

    ancestor = next((p for p in path.parents if p.is_dir()), None)
    if ancestor is None:
        return None, f"Not found: {raw}"
    missing = path.relative_to(ancestor).parts[0]
    return None, f"There is no folder '{missing}' in {ancestor.as_posix()}. {folder_summary(ancestor)}"


def _check_kind(path: Path, want: str) -> tuple[Path | None, str]:
    if want == "file" and path.is_dir():
        return None, f"{path.as_posix()} is a folder, not a file: list it, or search in it."
    if want == "dir" and not path.is_dir():
        return None, f"{path.as_posix()} is a file, not a folder: read it, or search in it."
    return path, ""


def _kind_ok(path: Path, want: str) -> bool:
    return want == "any" or (want == "dir") == path.is_dir()


def _near_names(folder: Path, name: str) -> list[Path]:
    """Entries of `folder` that are `name` up to case, or `name` without (or with another) extension."""
    wanted = name.lower()
    wanted_stem = Path(name).stem.lower() if Path(name).suffix else wanted
    try:
        entries = list(folder.iterdir())
    except OSError:
        return []
    exact = [e for e in entries if e.name.lower() == wanted]
    if exact:
        return sorted(exact)
    return sorted(e for e in entries if e.stem.lower() in (wanted, wanted_stem))


def folder_summary(folder: Path) -> str:
    """'It contains: a/, b/, c.txt (and 12 more).' for an error message."""
    try:
        entries = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError:
        return "It cannot be listed."
    if not entries:
        return "It is empty."
    names = [p.name + ("/" if p.is_dir() else "") for p in entries[:FOLDER_PREVIEW]]
    more = len(entries) - len(names)
    return "It contains: " + ", ".join(names) + (f" (and {more} more)." if more else ".")


# ---------------------------------------------------------------------------- reading


def size_text(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 / 1024:.1f} MB"


def _sniff_binary(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return b"\x00" in handle.read(4096)
    except OSError:
        return False


def _encoding(path: Path) -> str:
    """UTF-8 unless the start of the file is not; then Windows' Turkish code page, the common other case here."""
    try:
        with path.open("rb") as handle:
            sample = handle.read(65536)
    except OSError:
        return "utf-8"
    cut = sample.rfind(b"\n")
    if 0 < cut < len(sample) - 1:
        sample = sample[:cut]      # never judge a character split at the end of the sample
    try:
        sample.decode("utf-8")
        return "utf-8-sig"
    except UnicodeDecodeError:
        return "cp1254"


def _cut(line: str, limit: int = LINE_CHARS) -> str:
    line = line.rstrip()
    return line if len(line) <= limit else line[:limit] + f" ...[+{len(line) - limit} characters]"


def document_lines(path: Path) -> tuple[list[str], str]:
    """The text of a PDF or Word file as lines, and a short description ('PDF, 3 pages')."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise DocumentError("reading PDF files needs the pypdf package (pip install pypdf)") from exc
        try:
            reader = PdfReader(str(path))
            if reader.is_encrypted and not reader.decrypt(""):
                raise DocumentError("the PDF is password-protected")
            lines: list[str] = []
            pages = reader.pages
            for number, page in enumerate(pages, 1):
                if number > MAX_PDF_PAGES:
                    lines.append(f"(the remaining {len(pages) - MAX_PDF_PAGES} pages were not read)")
                    break
                text = page.extract_text() or ""
                lines.append(f"--- page {number} ---")
                lines.extend(line for line in text.splitlines() if line.strip())
        except DocumentError:
            raise
        except Exception as exc:  # noqa: BLE001 - a broken PDF is data for the model, not a crash
            raise DocumentError(f"the PDF could not be read ({exc})") from exc
        if not any(line.strip() and not line.startswith("--- page") for line in lines):
            raise DocumentError("this PDF has no text in it (probably scanned pages); it cannot be read "
                                "without text recognition")
        return lines, f"PDF, {len(pages)} page{'s' if len(pages) != 1 else ''}, text extracted"
    if suffix == ".docx":
        try:
            import docx
            from docx.table import Table
            from docx.text.paragraph import Paragraph
        except ImportError as exc:
            raise DocumentError("reading Word files needs the python-docx package (pip install python-docx)") from exc
        try:
            document = docx.Document(str(path))
            lines = []
            # Paragraphs and tables in the order they appear, not all paragraphs and then all tables.
            for child in document.element.body.iterchildren():
                tag = child.tag.rsplit("}", 1)[-1]
                if tag == "p":
                    text = Paragraph(child, document).text.strip()
                    if text:
                        lines.append(text)
                elif tag == "tbl":
                    for row in Table(child, document).rows:
                        cells = [cell.text.strip() for cell in row.cells]
                        if any(cells):
                            lines.append(" | ".join(cells))
        except Exception as exc:  # noqa: BLE001
            raise DocumentError(f"the Word file could not be read ({exc})") from exc
        return lines, "Word document, text extracted"
    raise DocumentError(f"{suffix} files are not supported")


class DocumentError(Exception):
    """A document that cannot be turned into text, with the reason in words."""


def read_window(path: Path, start_line: int = 1, end_line: int = 0) -> str:
    """
    Part of a file with line numbers, never more than WINDOW_CHARS of it.

    start_line counts from 1; a negative start_line counts from the end (-50: the last 50
    lines); 0 means the default: the start, or the end for a log. end_line 0 means "as far as
    fits". A file that fits whole is returned whole.
    """
    if start_line == 0:
        start_line = -200 if path.suffix.lower() in LOG_SUFFIXES and not end_line else 1
    name = path.name
    suffix = path.suffix.lower()
    try:
        size = path.stat().st_size
    except OSError as exc:
        return f"{name} cannot be read: {exc}"

    if suffix in DOCUMENT_SUFFIXES:
        if size > MAX_DOCUMENT_BYTES:
            return (f"{name} is a {size_text(size)} document, too large to read here (the limit is "
                    f"{size_text(MAX_DOCUMENT_BYTES)}).")
        try:
            lines, about = document_lines(path)
        except DocumentError as exc:
            return f"{name}: {exc}."
        return _window(name, about, iter(lines), start_line, end_line)

    if suffix in BINARY_SUFFIXES or _sniff_binary(path):
        return f"{name} is not a text file ({size_text(size)}); it cannot be read as text."
    if size > MAX_TEXT_BYTES:
        return f"{name} is {size_text(size)}, too large to read; search in it for what you need instead."
    try:
        with path.open(encoding=_encoding(path), errors="replace", newline=None) as handle:
            return _window(name, size_text(size), (line.rstrip("\r\n") for line in handle), start_line, end_line)
    except OSError as exc:
        return f"{name} cannot be read: {exc}"


def _window(name: str, about: str, lines: Iterator[str], start_line: int, end_line: int) -> str:
    """Number the lines and keep the window that was asked for, within the character budget."""
    budget = WINDOW_CHARS - 300      # room for the header and the footer
    tail = start_line < 0
    keep: deque[tuple[int, str]] = deque(maxlen=-start_line) if tail else deque()
    total = 0
    used = 0
    complete = True
    first = max(1, start_line) if not tail else 1
    for total, line in enumerate(lines, 1):
        if tail:
            keep.append((total, line))
            continue
        if total < first or (end_line and total > end_line):
            continue
        if not complete:
            continue
        entry = f"{total}| {_cut(line)}"
        if used + len(entry) + 1 > budget and keep:
            complete = False
            continue
        keep.append((total, line))
        used += len(entry) + 1

    if total == 0:
        return f"{name} is empty."
    if tail:
        # Keep the end: drop from the front of the tail until it fits.
        entries = [f"{n}| {_cut(text)}" for n, text in keep]
        while entries and sum(len(e) + 1 for e in entries) > budget:
            entries.pop(0)
            keep.popleft()
    if not keep:
        return f"{name} has {total} lines; line {first} is past the end."

    shown_first, shown_last = keep[0][0], keep[-1][0]
    body = "\n".join(f"{n}| {_cut(text)}" for n, text in keep)
    if shown_first == 1 and shown_last == total:
        return f"{name} ({about}, {total} lines):\n{body}"
    # A negative start_line shows as many of the last lines as fit, so the suggestion is generous.
    if tail:
        footer = (f"[Only the last lines are shown: {shown_first}-{shown_last} of {total}. Earlier lines are not "
                  f"shown here; the start: start_line=1. To find something specific, search the file.]")
    else:
        footer = (f"[Only lines {shown_first}-{shown_last} of {total} are shown; say nothing about the rest from "
                  f"this part. Another part: start_line=<line>; the end of the file: start_line=-200. To find "
                  f"something specific, search the file instead of reading all of it.]")
    return f"{name} ({about}): lines {shown_first}-{shown_last} of {total}\n{body}\n{footer}"


# ---------------------------------------------------------------------------- searching


def _normalise(text: str) -> str:
    """Lowercase, with _ and - read as spaces: 'max retries' finds MAX_RETRIES and max-retries."""
    return re.sub(r"[_\-]+", " ", text.lower())


def _words(query: str) -> list[str]:
    return [w for w in re.findall(r"\w+", _normalise(query)) if len(w) >= 4]


def _walk(root: Path, started: float) -> Iterator[Path]:
    documents = 0
    for folder, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for filename in sorted(filenames):
            if time.perf_counter() - started > SEARCH_MAX_SECONDS:
                return
            path = Path(folder) / filename
            suffix = path.suffix.lower()
            if suffix in BINARY_SUFFIXES:
                continue
            if suffix in DOCUMENT_SUFFIXES:
                documents += 1
                if documents > MAX_DOCUMENTS_IN_SEARCH:
                    continue
            yield path


def _lines_of(path: Path, limit_bytes: int) -> Iterator[str]:
    suffix = path.suffix.lower()
    if suffix in DOCUMENT_SUFFIXES:
        try:
            if path.stat().st_size > min(limit_bytes, MAX_DOCUMENT_BYTES):
                return
            yield from document_lines(path)[0]
        except OSError:
            return
        except DocumentError:
            return
        return
    try:
        if path.stat().st_size > limit_bytes or _sniff_binary(path):
            return
        with path.open(encoding=_encoding(path), errors="replace", newline=None) as handle:
            for line in handle:
                yield line.rstrip("\r\n")
    except OSError:
        return


def search(query: str, path: Path) -> str:
    """
    The lines that contain `query` in a file, or in every readable file under a folder.

    Case does not matter, and _ or - count as spaces. When no line contains the whole
    query, the lines that contain the most of its longer words are shown instead, and
    said to be the closest, not exact.
    """
    query = (query or "").strip()
    needle = _normalise(query)
    if not needle.strip():
        return "Nothing to search for: give a word or a name."
    started = time.perf_counter()
    single = path.is_file()
    files = [path] if single else _walk(path, started)
    limit = MAX_TEXT_BYTES if single else SEARCH_MAX_FILE_BYTES

    # Matches are counted, and only what can be shown is kept: a common word in a large log used
    # to keep every matching line in memory to show thirty of them (found in review).
    half = SEARCH_MAX_SHOWN // 2
    first: list[tuple[str, int, str]] = []
    last: deque[tuple[str, int, str]] = deque(maxlen=half)
    count = 0
    elsewhere: dict[str, int] = {}
    best, closest = 0, []
    words = _words(query)
    scanned = 0
    for file in files:
        if scanned >= SEARCH_MAX_FILES:
            break
        scanned += 1
        shown_name = file.name if single else file.relative_to(path).as_posix()
        for number, line in enumerate(_lines_of(file, limit), 1):
            folded = _normalise(line)
            if needle in folded:
                count += 1
                entry = (shown_name, number, line[:SEARCH_LINE_CHARS + 20])
                if len(first) < (half if single else SEARCH_MAX_SHOWN):
                    first.append(entry)
                elif single:
                    last.append(entry)
                elif shown_name in elsewhere or len(elsewhere) < SEARCH_MAX_FILES_COUNTED:
                    elsewhere[shown_name] = elsewhere.get(shown_name, 0) + 1
            elif words and not count:
                # The closest lines matter only while nothing has matched exactly.
                hits = sum(1 for w in words if w in folded)
                if hits > best:
                    best, closest = hits, [(shown_name, number, line[:SEARCH_LINE_CHARS + 20])]
                elif hits and hits == best and len(closest) < SEARCH_MAX_SHOWN:
                    closest.append((shown_name, number, line[:SEARCH_LINE_CHARS + 20]))
    timed_out = time.perf_counter() - started > SEARCH_MAX_SECONDS
    where = path.name if single else f"{path.as_posix()} ({scanned} files searched)"

    notes = []
    if timed_out or scanned >= SEARCH_MAX_FILES:
        notes.append("The search stopped early: search a smaller folder for a complete answer.")

    if count:
        verb = "lines contain" if count != 1 else "line contains"
        shown = [_match_line(m) for m in first]
        gap = count - len(first) - len(last)
        if single:
            if gap:
                shown.append(f"... {gap} more in between ...")
            shown.extend(_match_line(m) for m in last)
        elif elsewhere:
            listed = ", ".join(f"{name} ({n})" for name, n in list(elsewhere.items())[:10])
            shown.append(f"... and {count - len(first)} more in: {listed}")
        return _fit_lines(f'{count} {verb} "{query}" in {where}:', shown, notes)
    if closest:
        header = (f'No line contains "{query}" as written in {where}. The closest lines, with '
                  f'{best} of the words ({", ".join(words)}):')
        return _fit_lines(header, [_match_line(m) for m in closest], notes)
    return f'No line contains "{query}" in {where}.' + (" " + " ".join(notes) if notes else "")


def _match_line(entry: tuple[str, int, str]) -> str:
    name, number, text = entry
    return f"{name}:{number}: {_cut(text.strip(), SEARCH_LINE_CHARS)}"


def _fit_lines(header: str, shown: list[str], notes: list[str]) -> str:
    out = [header]
    used = len(header)
    for entry in shown:
        if used + len(entry) + 1 > WINDOW_CHARS - 200:
            out.append("... (more lines; search for something more specific)")
            break
        out.append(entry)
        used += len(entry) + 1
    out.extend(notes)
    return "\n".join(out)


# ---------------------------------------------------------------------------- listing


def listing(path: Path, depth: int = 1) -> str:
    """A folder's contents, `depth` levels down (1 to TREE_MAX_DEPTH), folders first, with file sizes."""
    depth = max(1, min(int(depth or 1), TREE_MAX_DEPTH))
    lines = [f"{path.as_posix()}/"]
    budget = WINDOW_CHARS - 200
    used = len(lines[0])
    hidden = 0

    def entries(folder: Path) -> list[Path] | None:
        try:
            return sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            return None

    def walk(folder: Path, level: int) -> None:
        nonlocal used, hidden
        items = entries(folder)
        indent = "  " * level
        if items is None:
            add(f"{indent}(cannot be listed)")
            return
        if used >= budget - 40:
            hidden += len(items)        # full already: count, do not walk a large tree for nothing
            return
        if not items and level == 1:
            add(f"{indent}(empty)")
        for item in items:
            if item.is_dir():
                skipped = item.name in SKIP_DIRS
                inner = entries(item)
                count = "" if inner is None else f"  ({len(inner)} item{'s' if len(inner) != 1 else ''})"
                if level < depth and not skipped and inner:
                    if not add(f"{indent}{item.name}/"):
                        hidden += 1
                        continue
                    walk(item, level + 1)
                elif not add(f"{indent}{item.name}/{count}"):
                    hidden += 1
            else:
                try:
                    size = size_text(item.stat().st_size)
                except OSError:
                    size = "?"
                if not add(f"{indent}{item.name}  {size}"):
                    hidden += 1

    def add(text: str) -> bool:
        nonlocal used
        if used + len(text) + 1 > budget:
            return False
        lines.append(text)
        used += len(text) + 1
        return True

    walk(path, 1)
    if hidden:
        lines.append(f"... {hidden} more entries not shown: list a subfolder, or use a smaller depth.")
    return "\n".join(lines)
