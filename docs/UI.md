# The window

`python -m ui` (or `start_halcyon_gui.bat`) opens Halcyon in a desktop window. It has:

- the conversation, with a copy button on every message and every code block;
- the saved chats on the left, which you can open, rename, pin and delete;
- a live status: loading, ready, listening, thinking or speaking;
- a message box and a microphone button.

It is the same assistant as `python -m voice.cli`: the same model, tools, modes and safety rules.

The direction is a workspace in the spirit of Claude Code and Cursor, with Halcyon's own take on it: local, spoken as well as typed, and asking before it does anything. Past conversations are the first part of that. Still to come: projects, the context a conversation uses, and a panel that shows code and sources.

## How it is built

| Part | What it does |
|---|---|
| `ui/session.py` | One conversation as a stream of small events: `state`, `user`, `delta`, `assistant_done`, `error`, `info`, `chats`, `chat` and `conversation`. It loads the model, answers typed messages and runs the voice loop on background threads, so the window never freezes. It saves what it shows and switches between chats. It has no window code, so it is tested without one (`tests/test_ui_session.py`, `tests/test_history.py`). |
| `ui/history.py` | The saved chats, in one SQLite file in your own data folder (`%LOCALAPPDATA%\Halcyon\history.db`). |
| `ui/app.py` | The window, drawn by the web view Windows already has (Edge WebView2) through pywebview. It also holds the bridge the page calls: `settings`, `ready`, `send`, `mic`, `chats`, `new_chat`, `open_chat`, `rename_chat`, `pin_chat`, `delete_chat`. Every public attribute of the bridge is reachable from the page, so it has only those, and a test keeps it that way. |
| `ui/web/` | The page: HTML, CSS and a small script. Replies are escaped before the little formatting there is (code blocks, inline code, bold), because a model can be made to write HTML. |

**Design.** Calm and plain: the colours of a dark sea with one turquoise accent. Motion happens only where the state changes, and none at all when the system asks for reduced motion.

**Language.** The labels are Turkish or English. The default is the first language in Windows Settings > Language. The web view's own choice was not used because it follows the display language, which was English on a machine whose user writes Turkish. The TR/EN switch at the bottom of the chat list changes it, and the choice is remembered.

## Past conversations

- **Saving.** A chat is saved from its first message. Its title is that message, cut at a word, and you can rename it. Pinned chats come first, then the rest are grouped by day.
- **What is kept.** Your messages and the replies, as the window showed them, each marked typed or spoken. A reply cut off by speaking over it is marked "interrupted", and one an error cut short is marked as such: it is shown with a note and not given back to the model as an answer. Tool results are not kept, and neither are error messages.
- **Reopening.** A chat you reopen continues where it stopped. Its questions and answers become the model's history again, cut to the usual length. A file read back then is read again if you ask about it, because tool results were not saved.
- **Switching chats** is refused while a reply is being written or the microphone is on: both own the model.
- **Where it lives.** Only on this computer, never in the cloud or the repository. On Linux and macOS the folder and file are readable by their owner only; on Windows the user's own profile already keeps other users out. If the file cannot be opened (a folder that cannot be written, a damaged file), the window still opens, says chats cannot be saved, and works without them. `HALCYON_DATA=<folder>` moves the file; `python -m ui --no-history` keeps nothing.
- **Deleting.** Deleting really deletes. SQLite normally leaves deleted text in the file's free pages until the file is rebuilt. With `secure_delete` on, the freed pages are overwritten, and a test reads the file back to check. With it off, the same test finds the deleted text.

## Rules it keeps

- **The microphone opens only when you press its button.** Nothing else in the window or the session opens it.
- **One conversation at a time.** While a reply is being written, or while the microphone is on, the message box is off. Otherwise the voice loop and a typed message would use the model at once.
- **Typed messages get the typed setup and spoken ones the spoken setup.**
  - Typed: a written prompt that allows code blocks and longer answers, 1200 tokens for a reply, and 8 tool rounds.
  - Spoken: two sentences, no symbols, the profile's short budget, and 4 tool rounds.
  - The switch happens when the microphone goes on or off; the model stays loaded (docs/MODES.md, "Typing and speaking").

## Checked

**Tests.** Forty-six tests cover the session, the store and the bridge:

- the events arrive in order, and only one reply is written at a time;
- a model that fails to load or fails half way, and a store that fails, are reported without stopping the conversation;
- the session never opens the microphone, and the microphone and a typed reply never share the model;
- what is saved, and how it is saved;
- reopening a chat, for a model that is loaded and for one still loading;
- switching is refused while busy, and only the chat being written cannot be deleted;
- deleted text is gone from the file, and a long reopened chat is cut;
- the page sees only the bridge's calls and is opened by a plain file address.

**The real window, driven through its own page**, with the 4B model the planner chose, in Turkish, with the history in a temporary folder:

- The model loaded in 25 s.
- A request for a Sieve of Eratosthenes function came back complete, in a code block, in 7.8 s (1196 characters). Before, the spoken budget cut a reply at 160 tokens.
- "Kaç tane modun var?" was answered with the three modes and the current one.
- A new chat, then reopening the first one: its two messages came back. "What is the time complexity of this function?" was answered as O(n log log n), so the model had the reopened history.
- Both chats were in the file with 4 and 2 messages.

**Qodo's review of #6** found six problems, all reproduced and pinned by tests that fail on the old code:

- the TR/EN choice was lost on every restart (pywebview's private mode; the window now keeps its page storage in the Halcyon data folder, checked by closing and reopening it);
- the history folder could be readable by other users on Linux;
- a history that could not open stopped the window from starting;
- a mode declined in one chat stayed quiet in the next;
- a rename being typed was wiped when a reply finished;
- a reply cut short by an error was saved as if it were finished.

**Things found and fixed along the way:**

- Nothing could be selected or copied, because pywebview turns text selection off unless `text_select=True`.
- `python -m ui --demo` had never worked. WebView2 read `index.html?demo=1` as a file name and showed "File not found". The page is now opened by a plain file address and asks the bridge for its settings.

**Without a model.** `python -m ui --demo`, or the page opened in a browser, plays sample chats with no model, for design work. Every control works there: open, new chat, rename, pin, delete, copy, language, and the narrow layout.

**Not yet:**

- The spoken path has been tested with a fake voice loop, not with a live microphone.
- The window has been run on Windows only.
- Projects, context and the code panel are still to come.
- The VRAM planner reserves room for speech recognition even though the window only loads it when the microphone is pressed, so with about 6.7 GB free it picks the 4B model.
