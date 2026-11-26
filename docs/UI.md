# The window

`python -m ui` (or `start_halcyon_gui.bat`) opens Halcyon in a desktop window: the conversation, a live status (loading, ready, listening, thinking, speaking), a message box and a microphone button. It is the same assistant as `python -m voice.cli`: the same model, tools, modes and safety rules.

This is the first version on purpose. The direction is a workspace in the spirit of Claude Code and Cursor (projects, past conversations you can rename and pin, the context a conversation uses, a panel that shows code and sources), with Halcyon's own take on it: local, spoken as well as typed, and asking before it does anything.

## How it is built

| Part | What it does |
|---|---|
| `ui/session.py` | One conversation as a stream of small events (`state`, `user`, `delta`, `assistant_done`, `error`, `info`). Loads the model, answers typed messages and runs the voice loop on background threads, so the window never freezes. No window code, so it is tested without one (`tests/test_ui_session.py`). |
| `ui/app.py` | The window, drawn by the web view Windows already has (Edge WebView2) through pywebview, and the bridge the page calls: `ready`, `send`, `mic`. Every public attribute of the bridge is reachable from the page, so it has only those (a test keeps it that way). |
| `ui/web/` | The page: HTML, CSS and a small script. Replies are escaped before the little formatting there is (code blocks, inline code, bold), because a model can be made to write HTML. |

Design: calm and plain, the colours of a dark sea with one turquoise accent; motion only where the state changes, and none when the system asks for reduced motion. Labels follow the system language (Turkish or English).

## Rules it keeps

- **The microphone opens only when you press its button.** Nothing else in the window or the session opens it.
- **One conversation at a time.** While a reply is being written, or while the microphone is on, the message box is off: the voice loop and a typed message would otherwise use the model at once.
- **A typed message gets the typed setup** (more tool rounds) and a spoken one the spoken setup, as in the terminal.

## Checked

- 13 tests for the session and the bridge: the events in order, one reply at a time, a model that fails to load or fails half way, the microphone never opened by the session, events sent before the page was ready kept in order, model text that cannot break out of the script it is sent in, and the page seeing only the bridge's four calls.
- The real window, driven through its own page: the model loaded in 22 s, a message typed into the box and sent with the button came back as "The capital of France is Paris." 0.6 s later, the microphone stayed off.
- `python -m ui --demo`, or the page opened in a browser, plays sample messages with no model, for design work.

Not yet: the spoken path has been tested with a fake voice loop, not with a live microphone; the window has been run on Windows only.
