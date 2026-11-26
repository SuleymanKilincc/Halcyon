"""
The Halcyon window: the page in ui/web, drawn by the system's web view, talking to a Session.

    python -m ui                 # the assistant, in a window
    python -m ui --demo          # the window with sample messages and no model (for design work)

pywebview draws the page with the web view Windows already has (Edge WebView2) and lets the page
call the Python methods of `Bridge` as `window.pywebview.api.<name>()`. Events go the other way
by running `window.halcyon.receive(<json>)` in the page. Nothing here opens the microphone: only
the page's microphone button does, through Bridge.mic.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path

WEB = Path(__file__).resolve().parent / "web"


class Bridge:
    """
    What the page may call. Kept small on purpose: every public attribute of this object is exposed to
    the page, and pywebview walks into them (a public `window` attribute made it walk the whole native
    window from the wrong thread). So the only public names are the page's calls and `emit`.
    """

    def __init__(self, language: str = "en", demo: bool = False) -> None:
        self._language, self._demo = language, demo
        self._window = None
        self._session = None
        self._ready = threading.Event()
        self._pending: list[dict] = []
        self._lock = threading.Lock()

    def _attach(self, window, session) -> None:  # noqa: ANN001
        self._window, self._session = window, session

    # Called by the page ------------------------------------------------------

    def settings(self) -> dict:
        """What the page cannot read from its own address (see page_url): its language, and demo or not."""
        return {"language": self._language, "demo": self._demo}

    def ready(self) -> bool:
        """The page has loaded and can draw events: send what came before it, in order."""
        with self._lock:
            # Drained under the lock, so an event emitted meanwhile waits and comes after these
            # rather than overtaking them (found in review).
            for event in self._pending:
                self._push(event)
            self._pending = []
            self._ready.set()
        return True

    def send(self, text: str) -> bool:
        return self._session.send_text(text) if self._session else False

    def mic(self, on: bool) -> bool:
        if self._session is None:
            return False
        return self._session.mic_on() if on else self._session.mic_off()

    def chats(self) -> list:
        return self._session.chats() if self._session else []

    def new_chat(self) -> bool:
        return self._session.new_chat() if self._session else False

    def open_chat(self, chat_id: int) -> bool:
        return self._session.open_chat(int(chat_id)) if self._session else False

    def rename_chat(self, chat_id: int, title: str) -> bool:
        return self._session.rename_chat(int(chat_id), str(title)) if self._session else False

    def pin_chat(self, chat_id: int, pinned: bool) -> bool:
        return self._session.pin_chat(int(chat_id), bool(pinned)) if self._session else False

    def delete_chat(self, chat_id: int) -> bool:
        return self._session.delete_chat(int(chat_id)) if self._session else False

    # Called by the session -------------------------------------------------

    def emit(self, event: dict) -> None:
        with self._lock:
            if not self._ready.is_set():
                self._pending.append(event)
                return
            self._push(event)

    def _push(self, event: dict) -> None:
        if self._window is not None:
            self._window.evaluate_js(f"window.halcyon && window.halcyon.receive({json.dumps(event)})")


def system_language() -> str:
    """
    "tr" or "en": the first of the user's preferred languages (Windows Settings > Language).

    The web view's own language follows the Windows display language and regional format,
    which were both English on a machine whose user writes Turkish and put Turkish first in
    the language list: the window came up in English. The page can still be switched.
    """
    names: list[str] = []
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\International\User Profile") as key:
                names = list(winreg.QueryValueEx(key, "Languages")[0])
        except OSError:
            names = []
    if not names:
        import locale

        names = [locale.getlocale()[0] or ""]
    first = (names[0] if names else "").lower()
    return "tr" if first.startswith(("tr", "turkish")) else "en"


def page_url() -> str:
    """
    The page, as a file address with nothing after it. WebView2 reads a query string as part of the
    file name: index.html?demo=1 opened "File not found", so `--demo` never worked in the window.
    The page asks the bridge for its settings instead (Bridge.settings).
    """
    return (WEB / "index.html").as_uri()


def open_history():  # noqa: ANN201
    """
    The saved chats, or None and the reason. A folder that cannot be written or a damaged file
    must not keep the window from opening (found in review): the session runs, unsaved.
    """
    from ui.history import History

    try:
        return History(), None
    except Exception as exc:  # noqa: BLE001
        return None, f"Chats cannot be saved this time: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--demo", action="store_true", help="sample messages, no model")
    parser.add_argument("--debug", action="store_true", help="allow the web view's developer tools")
    parser.add_argument("--no-history", action="store_true", help="keep no conversations on disk")
    args = parser.parse_args()

    import webview

    from ui.history import default_path
    from ui.session import Session

    bridge = Bridge(language=system_language(), demo=args.demo)
    history, problem = (None, None) if args.demo or args.no_history else open_history()
    if problem:
        bridge.emit({"type": "error", "message": problem})    # shown once the page is ready
    # text_select: pywebview turns selecting text off by default, so nothing could be copied.
    window = webview.create_window("Halcyon", page_url(), js_api=bridge,
                                   width=1180, height=760, min_size=(420, 480), background_color="#0f1b24",
                                   text_select=True)
    session = None if args.demo else Session(bridge.emit, history=history)
    bridge._attach(window, session)
    if session is not None:
        session.start()
    try:
        # Not private: pywebview's default forgets the page's storage when the window closes, so
        # the TR/EN choice and the folded chat list were lost on every restart (found in review).
        webview.start(debug=args.debug, private_mode=False, storage_path=str(default_path().parent / "webview"))
    finally:
        if session is not None:
            session.close()
        if history is not None:
            history.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
