# The file and web tools, measured

A downloaded model can talk. It cannot read the end of a long log, open a PDF, find where a function is defined in a project, or open the page behind a search result. That is the work of the tools around it, and this page records how much of the difference they make, measured with the same models before and after.

## How it was measured

`bench/task_eval.py` runs the assistant the way it really runs: `core.llm.SpeechLLM` with its persona, its capability and environment statements, its tool loop and the cap on a tool result. Fifteen tasks (eleven in English, four in Turkish) are asked about a small project that the script generates in a temporary folder for every run:

| Task | What it needs |
|---|---|
| `readme_port` (TR), `yaml_value` | read one named file |
| `find_def`, `find_def_tr`, `deep_constant` | find a definition or a value somewhere in a folder tree (the last one four folders down) |
| `count_tests` | list a folder |
| `bug`, `bug_tr` | spot an off-by-one in a short function |
| `last_error`, `last_error_tr` | the last error of a 3000-line log, at character 164,000 |
| `pdf`, `docx` (TR) | a compressed PDF and a Word document |
| `missing` | a file that does not exist: say so, do not invent it |
| `research`, `research_tr` | the latest release of a library: the search snippets mention an older version, the releases page the right one |

The file tools are the real ones, so nothing on the user's disk is read. The web tools are fakes that answer the way the real ones of the code under test do (before: snippet text with no links, as the old wrapper returned; after: titles, links and snippets), so a research task is the same on every run and needs no network.

A task passes when the reply contains every expected fact, none of the forbidden ones, is in the language of the request, and the tools it needed were called. Generation is sampled, so every configuration was run with three seeds and each task is reported as passes out of 3. All the logs were judged again with the final rules (`--rescore`), so before and after are compared under one judge.

Machine: RTX 4060 Laptop 8 GB, 32 GB RAM, Ollama 0.40.18. Typed turns get 8 tool rounds, spoken ones 4; the old code had 4 for both.

## Results

Task runs passed, out of 45 (15 tasks, 3 seeds):

| Configuration | Before | After |
|---|---|---|
| `qwen3.5:9b`, the general model, typed | **14** | **37** |
| `qwen3.5:9b`, spoken (4 tool rounds) | 14 | **36** |
| `gemma4:e4b`, deep mode (Light pack) | 10 | **31** |
| `gemma4:26b-a4b`, deep mode (Standard pack) | 18 | **44** |

Per task (passes out of 3):

| Task | 9B before | 9B after | 9B spoken after | e4b before | e4b after | 26B before | 26B after |
|---|---|---|---|---|---|---|---|
| readme_port | 0 | 3 | 3 | 0 | 3 | 3 | 3 |
| yaml_value | 3 | 3 | 3 | 3 | 3 | 3 | 3 |
| find_def | 0 | 3 | 3 | 0 | 3 | 0 | 3 |
| deep_constant | 0 | 3 | 3 | 0 | 3 | 0 | 2 |
| count_tests | 3 | 3 | 3 | 3 | 3 | 3 | 3 |
| bug | 3 | 3 | 3 | 0 | 0 | 3 | 3 |
| bug_tr | 3 | 3 | 1 | 1 | 0 | 3 | 3 |
| last_error | 0 | 2 | 3 | 0 | 2 | 0 | 3 |
| pdf | 0 | 3 | 3 | 0 | 3 | 0 | 3 |
| docx | 0 | 0 | 0 | 0 | 2 | 0 | 3 |
| missing | 2 | 3 | 3 | 3 | 3 | 3 | 3 |
| research | 0 | 3 | 3 | 0 | 3 | 0 | 3 |
| find_def_tr | 0 | 3 | 3 | 0 | 0 | 0 | 3 |
| last_error_tr | 0 | 2 | 2 | 0 | 0 | 0 | 3 |
| research_tr | 0 | 0 | 0 | 0 | 3 | 0 | 3 |

With the new tools the 26B model passed every task in two of the three seeds; its one failure is the empty answer described below. Before, five tasks failed for **every** model and every seed, the 26B one included: the end of the log, the PDF, the Word file and both research tasks. A bigger model did not help, because the tools could not do them.

## What was wrong, and what changed

| Measured before | Cause | Now |
|---|---|---|
| The last error of a long log was out of reach; models said the log "appears truncated" | `read_file` returned the whole file and the loop kept its first 4000 characters | Files are read as a window of at most 3500 characters with line numbers, from any line or from the end, and the window says how to read further (`core/files.py`) |
| "I cannot read PDF files"; a Word file "is binary" | They came back as compressed bytes | PDF (pypdf) and Word (python-docx) are read as text |
| "I could not finish that" while looking for a definition | One folder per round, and four rounds | `search_files` finds text in a file or a folder tree in one call; `list_directory` shows a project several levels deep; typed turns get 8 rounds and the last round must answer from what was found |
| Two models asked for `README` and were told it did not exist | The persona says "name files without the extension", and that leaked into tool calls | A name that matches exactly one file is used (and said so); one that matches nothing comes back with what the folder contains; the persona says the rule is for speech only |
| The latest release given as an old version from a snippet, or "no such library" | Search results had no links, so the page could not be opened | Results carry title, link and snippet, and say snippets can be out of date; a page can be asked for the parts that mention a word (`core/web.py`) |
| "Let me check the other files." and nothing else | The model announced an action and stopped | A short reply that only announces an action, or asks leave to read, is sent back once to act |
| Several large reads could overflow the 8k context, which Ollama handles by silently dropping the oldest tokens, the system prompt first | No budget | The messages are fitted before every round: older tool results shortened first, the question and the newest result kept |

## What the live runs found that the unit tests did not

- **Every tool round crashed** on the first run of the new loop: "Object of type ToolCall is not JSON serializable". Sizing the context used `json.dumps` on the tool calls, and the real client returns `ToolCall` objects where the unit tests used dicts. A regression test now uses the real type.
- **Web search had been broken in use.** The LangChain wrapper it went through needs a package that is not installed ("Could not import ddgs"), so every search failed. The tool now calls the DuckDuckGo client directly and tries its other backends when one comes back empty.
- **The judge was too strict.** It failed "forty-five seconds" (the spoken persona writes numbers in words), "cannot be found", "I was unable to find the file" and "There is no database.py file in that folder". Numbers in words and more ways of saying "not there" now count, and every log, before and after, was judged again with the same rules.
- **An empty answer.** Once, after nine rounds of searching, the 26B model ended with an empty reply, which the old loop passed on as the answer. An empty reply is now sent back once like an announcement, and an empty final answer says "I could not finish that" (this was added after the measured run).
- **The 26B model sometimes fails to load right after the 9B one** ("llama-server process has terminated ... CUDA error: shared object initialization failed"), and loads on a second attempt. In the assistant a failed switch rolls back to the general model and says so; in the benchmark it cost a run.

## What is still weak

- **Turkish, with the 9B model.** It still sometimes says what it would do ("Dosyayı okuyarak toplantı tarihini bulacağım", "web araması yapayım mı?") instead of doing it, even after being sent back once. The Word task and the Turkish research task were never passed by it.
- **The Light model in Turkish and on the bug tasks.** It sometimes believes a path is out of its reach, asks for one it was given, or searches a file for the word "bug".
- **Fixed tasks on a small generated project**, three seeds, one machine. The gaps (14 to 37 of 45) are far larger than the seed-to-seed variation; a one-task difference is not.
- **The web was faked** to make the research tasks repeatable. The real search was checked by hand (titles, links and snippets came back), not measured.

## Re-running it

```bash
python -m bench.task_eval --seeds 7,8,9                         # the general model, typed
python -m bench.task_eval --spoken --seeds 7,8,9                # the rounds a spoken turn gets
python -m bench.task_eval --deep gemma4:26b-a4b --seeds 7,8,9   # a deep-mode model and prompt
python -m bench.task_eval --rescore run.log                     # judge a saved log with the current rules
```
