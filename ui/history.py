"""
Conversations kept on this computer, so the window can list them, reopen them and carry on.

One SQLite file, in the user's own application data folder (never the cloud, never the repo):

    Windows   %LOCALAPPDATA%\\Halcyon\\history.db
    elsewhere ~/.local/share/halcyon/history.db
    HALCYON_DATA=<folder> puts it somewhere else; `python -m ui --no-history` keeps nothing.

What is kept is what the page showed: the user's messages and the replies, with how each was
given (typed or spoken). Tool results are not kept, and neither are errors.

Deleting means deleting: `secure_delete` makes SQLite overwrite the freed pages with zeros, so a
deleted conversation cannot be read back out of the file afterwards, and the journal is the
default rollback one (a write-ahead log would keep old pages in a second file for a while).

The page and the session call this from different threads, so one connection is shared under
a lock. Pure Python with the standard library; tests use a file in a temporary folder.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import threading
import time
from pathlib import Path

TITLE_CHARS = 48

SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    id       INTEGER PRIMARY KEY,
    title    TEXT    NOT NULL,
    pinned   INTEGER NOT NULL DEFAULT 0,
    created  REAL    NOT NULL,
    updated  REAL    NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id       INTEGER PRIMARY KEY,
    chat_id  INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role     TEXT    NOT NULL,
    text     TEXT    NOT NULL,
    via      TEXT    NOT NULL DEFAULT 'text',
    status   TEXT    NOT NULL DEFAULT '',
    created  REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS messages_by_chat ON messages(chat_id, id);
"""


def default_path(env: dict | None = None) -> Path:
    env = os.environ if env is None else env
    if env.get("HALCYON_DATA"):
        return Path(env["HALCYON_DATA"]) / "history.db"
    if sys.platform == "win32" and env.get("LOCALAPPDATA"):
        return Path(env["LOCALAPPDATA"]) / "Halcyon" / "history.db"
    return Path.home() / ".local" / "share" / "halcyon" / "history.db"


def _owner_only(path: Path, mode: int) -> None:
    """
    Chats are private: on Linux and macOS the folder and the file are made readable by their owner
    only, whatever the umask (found in review). On Windows the folder is in the user's own
    profile, whose access list already keeps other users out; chmod there cannot express it.
    """
    if os.name == "posix":
        os.chmod(path, mode)


def title_from(text: str) -> str:
    """A chat's first title: its first message on one line, cut at a word."""
    line = " ".join(text.split())
    if len(line) <= TITLE_CHARS:
        return line or "…"
    cut = line[:TITLE_CHARS].rsplit(" ", 1)[0] or line[:TITLE_CHARS]
    return cut.rstrip(" ,.;:") + "…"


class History:
    def __init__(self, path: Path | str | None = None, clock=time.time) -> None:  # noqa: ANN001
        self.path = Path(path) if path is not None else default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _owner_only(self.path.parent, 0o700)
        if not self.path.exists():
            self.path.touch()
        _owner_only(self.path, 0o600)
        self._clock = clock
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        try:
            self._db.row_factory = sqlite3.Row
            self._db.execute("PRAGMA foreign_keys = ON")
            self._db.execute("PRAGMA secure_delete = ON")
            self._db.executescript(SCHEMA)
            self._db.commit()
        except sqlite3.Error:
            self._db.close()        # a damaged file: nothing left open behind the error
            raise

    # ------------------------------------------------------------------ writing

    def create(self, title: str) -> int:
        now = self._clock()
        with self._lock, self._db:
            cursor = self._db.execute("INSERT INTO chats (title, created, updated) VALUES (?, ?, ?)",
                                      (title_from(title), now, now))
            return int(cursor.lastrowid)

    def add(self, chat_id: int, role: str, text: str, via: str = "text", status: str = "") -> bool:
        now = self._clock()
        with self._lock, self._db:
            if self._db.execute("SELECT 1 FROM chats WHERE id = ?", (chat_id,)).fetchone() is None:
                return False            # deleted while the reply was being written
            self._db.execute("INSERT INTO messages (chat_id, role, text, via, status, created) "
                             "VALUES (?, ?, ?, ?, ?, ?)", (chat_id, role, text, via, status, now))
            self._db.execute("UPDATE chats SET updated = ? WHERE id = ?", (now, chat_id))
            return True

    def rename(self, chat_id: int, title: str) -> bool:
        title = " ".join((title or "").split())[:120]
        if not title:
            return False
        with self._lock, self._db:
            return self._db.execute("UPDATE chats SET title = ? WHERE id = ?", (title, chat_id)).rowcount > 0

    def pin(self, chat_id: int, pinned: bool) -> bool:
        with self._lock, self._db:
            return self._db.execute("UPDATE chats SET pinned = ? WHERE id = ?",
                                    (1 if pinned else 0, chat_id)).rowcount > 0

    def delete(self, chat_id: int) -> bool:
        with self._lock, self._db:
            return self._db.execute("DELETE FROM chats WHERE id = ?", (chat_id,)).rowcount > 0

    # ------------------------------------------------------------------ reading

    def chats(self) -> list[dict]:
        """Pinned first, then the most recently used."""
        with self._lock:
            rows = self._db.execute("SELECT id, title, pinned, updated FROM chats "
                                    "ORDER BY pinned DESC, updated DESC, id DESC").fetchall()
        return [{"id": r["id"], "title": r["title"], "pinned": bool(r["pinned"]), "updated": r["updated"]}
                for r in rows]

    def exists(self, chat_id: int) -> bool:
        with self._lock:
            return self._db.execute("SELECT 1 FROM chats WHERE id = ?", (chat_id,)).fetchone() is not None

    def messages(self, chat_id: int) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT role, text, via, status FROM messages WHERE chat_id = ? ORDER BY id",
                                    (chat_id,)).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._db.close()
