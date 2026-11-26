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
    window from the wrong thread). So the only public names are the page's four calls and `emit`.
    """

    def __init__(self) -> None:
        self._window = None
        self._session = None
        self._ready = threading.Event()
        self._pending: list[dict] = []
        self._lock = threading.Lock()

    def _attach(self, window, session) -> None:  # noqa: ANN001
        self._window, self._session = window, session

    # Called by the page ------------------------------------------------------

    def ready(self) -> bool:
        """The page has loaded and can draw events: send what came before it."""
        with self._lock:
            pending, self._pending = self._pending, []
            self._ready.set()
        for event in pending:
            self._push(event)
        return True

    def send(self, text: str) -> bool:
        return self._session.send_text(text) if self._session else False

    def mic(self, on: bool) -> bool:
        if self._session is None:
            return False
        return self._session.mic_on() if on else self._session.mic_off()

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--demo", action="store_true", help="sample messages, no model")
    parser.add_argument("--debug", action="store_true", help="allow the web view's developer tools")
    args = parser.parse_args()

    import webview

    from ui.session import Session

    bridge = Bridge()
    url = (WEB / "index.html").as_uri() + ("?demo=1" if args.demo else "")
    window = webview.create_window("Halcyon", url, js_api=bridge, width=980, height=720, min_size=(420, 480),
                                   background_color="#0f1b24")
    session = None if args.demo else Session(bridge.emit)
    bridge._attach(window, session)
    if session is not None:
        session.start()
    try:
        webview.start(debug=args.debug)
    finally:
        if session is not None:
            session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
