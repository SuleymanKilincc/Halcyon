"""
Can Halcyon do the technical work it is asked for? Files, code and research, through its own tool loop.

    python -m bench.task_eval                                # the general model of the 8 GB profile
    python -m bench.task_eval --deep gemma4:26b-a4b          # a deep-mode model with the deep-mode prompt
    python -m bench.task_eval --only pdf,last_error          # some tasks only
    python -m bench.task_eval --seeds 7,8,9                  # three runs; each task reported as passes out of 3
    python -m bench.task_eval --spoken                       # the tool rounds a spoken turn gets

Unlike bench/code_eval.py, which asks a model for code over the raw API, this runs the
assistant as it really runs: core.llm.SpeechLLM with its persona, its capability and
environment statements, its four-round tool loop and its 4000-character cap on a tool
result. The file tools are the real ones from tools.py, pointed at a small project that
is generated in a temporary folder for each run (a nested package, a 3000-line log, a
buggy function, a PDF, a Word file, a YAML config), so nothing on the user's disk is
read. The web tools are fakes that answer like the real ones (the search returns snippet
text without links, as DuckDuckGoSearchRun does), so a research task is the same on every
run and needs no network.

Generation is sampled (temperature 0.4), so one run of a task is a coin with a bias, not a
verdict: the same model passed a task in one run and failed it in the next. Each run is
seeded, and --seeds runs the whole set once per seed and reports every task as passes out of
the number of seeds. The tools the fakes imitate are those of the code under test: before
core/web.py existed the search returned snippets only, after it titles, links and snippets.

A task passes when the reply contains every expected fact (each group is "any of these
words"), contains none of the forbidden ones, is in the language of the request, and the
tools it needed were called. The checks are keyword rules, so every reply is printed for a
person to read as well; the totals are for finding what is broken, not a certificate.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

# ----------------------------------------------------------------------------- the project

README = """# Weatherline

A small service that collects readings from weather stations.

## Running it

    python -m weatherline

The server listens on port 8080 by default; set WEATHERLINE_PORT to change it.
Readings are stored for 90 days.
"""

SETTINGS = '''"""Configuration loading."""

import yaml


def parse_config(path):
    """Read the YAML file at `path` and fill in defaults."""
    with open(path) as handle:
        data = yaml.safe_load(handle) or {}
    data.setdefault("timeout", 30)
    return data
'''

CLIENT = '''"""HTTP client used to push readings upstream."""

MAX_RETRIES = 7
BACKOFF_SECONDS = 2.5


def push(reading, session):
    for attempt in range(MAX_RETRIES):
        if session.post("/readings", json=reading).ok:
            return True
    return False
'''

CALC = '''"""Small statistics helpers."""


def average(values):
    """The arithmetic mean of `values`."""
    total = 0
    for i in range(1, len(values)):
        total += values[i]
    return total / len(values)


def spread(values):
    return max(values) - min(values)
'''

APP_YAML = """server:
  host: 0.0.0.0
  port: 8080
storage:
  retention_days: 90
network:
  timeout: 45
"""


def _log_lines() -> str:
    lines = []
    for i in range(3000):
        minute, second = divmod(i, 60)
        stamp = f"2026-11-20 0{minute // 60}:{minute % 60:02d}:{second:02d}"
        if i == 412:
            lines.append(f"{stamp} ERROR station 17 sent a malformed reading")
        elif i == 2950:
            lines.append(f"{stamp} ERROR write failed: disk quota exceeded on /var/data")
        else:
            lines.append(f"{stamp} INFO reading stored from station {i % 40}")
    return "\n".join(lines) + "\n"


def _write_pdf(path: Path) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    page = canvas.Canvas(str(path), pagesize=A4)          # compressed text streams, like real PDFs
    page.drawString(72, 760, "Weatherline Station WS-4: Electrical Specification")
    page.drawString(72, 730, "Supply: 12 to 48 V DC. Maximum input voltage: 48 V.")
    page.drawString(72, 710, "Typical power draw: 3.2 W. Operating temperature: -30 to 60 C.")
    page.save()


def _write_docx(path: Path) -> None:
    import docx

    document = docx.Document()
    document.add_heading("Haftalık toplantı", level=1)
    document.add_paragraph("Ekip toplantısı her hafta Perşembe saat 14:00'te yapılır.")
    document.add_paragraph("Gündem: istasyon 17'deki bozuk veriler.")
    document.save(str(path))


def build_project(root: Path) -> None:
    """The small project every file task is asked about."""
    files = {
        "README.md": README,
        "src/app/settings.py": SETTINGS,
        "src/app/__init__.py": "",
        "src/app/network/__init__.py": "",
        "src/app/network/client.py": CLIENT,
        "src/calc.py": CALC,
        "config/app.yaml": APP_YAML,
        "logs/server.log": _log_lines(),
        "tests/test_settings.py": "def test_defaults():\n    pass\n",
        "tests/test_calc.py": "def test_average():\n    pass\n",
        "tests/test_client.py": "def test_push():\n    pass\n",
    }
    for relative, text in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    (root / "docs").mkdir(exist_ok=True)
    _write_pdf(root / "docs" / "spec.pdf")
    _write_docx(root / "docs" / "meeting.docx")


# ----------------------------------------------------------------------------- the web

SEARCH_SNIPPETS = (
    "Zephyrine is a Python library for streaming sensor data. Zephyrine 3.2 adds async readers and "
    "drops Python 3.8. Release notes - zephyrine.dev. Installing Zephyrine with pip install zephyrine. "
    "Zephyrine changelog: all versions are listed on the project's releases page."
)
RELEASE_PAGE = (
    "Zephyrine releases\n3.4.0 (2026-09-02): latest release. Adds Parquet export and a retry policy.\n"
    "3.3.1 (2026-06-14): bug fixes.\n3.2.0 (2026-02-10): async readers, Python 3.8 dropped."
)


# What a search engine would return, as data. The snippets deliberately do not say which version
# is the latest (one mentions an older one); the releases page does.
SEARCH_RESULTS = [
    {"title": "Zephyrine - streaming sensor data in Python", "href": "https://zephyrine.dev/",
     "body": "Zephyrine is a Python library for streaming sensor data. Zephyrine 3.2 adds async readers "
             "and drops Python 3.8."},
    {"title": "Releases - Zephyrine", "href": "https://zephyrine.dev/releases",
     "body": "Release notes and changelog for every Zephyrine version."},
    {"title": "zephyrine - PyPI", "href": "https://pypi.org/project/zephyrine/",
     "body": "pip install zephyrine. A Python library for streaming sensor data."},
]


def _web_module():
    """core.web when the code under test has it (the new tools); None for the old ones."""
    try:
        from core import web
    except ImportError:
        return None
    return web


class FakeSearch:
    """Answers the way the real search_web of the code under test does, from fixed results."""

    name = "search_web"

    def invoke(self, arguments: dict) -> str:
        query = str(arguments.get("query", ""))
        found = "zephyrine" in query.lower()
        web = _web_module()
        if web is None:     # the old tool: DuckDuckGoSearchRun's snippet text, no links
            return SEARCH_SNIPPETS if found else "No good DuckDuckGo Search Result was found"
        return web.format_search_results(query, SEARCH_RESULTS if found else [])


class FakeFetch:
    """Answers the way the real fetch_webpage of the code under test does, from a fixed page."""

    name = "fetch_webpage"

    def invoke(self, arguments: dict) -> str:
        url = str(arguments.get("url", ""))
        if "zephyrine" not in url.lower():
            return f"Error fetching webpage: 404 Client Error: Not Found for url: {url}"
        web = _web_module()
        if web is None:
            return f"Content from {url}:\n\n{RELEASE_PAGE}"
        return web.page_view(url, RELEASE_PAGE, str(arguments.get("find") or ""))


class Recorder:
    """Wraps a tool and records each call with its arguments."""

    def __init__(self, tool: Any, log: list[str]) -> None:  # noqa: ANN401
        self.tool, self.name, self.log = tool, tool.name, log

    def invoke(self, arguments: dict) -> Any:  # noqa: ANN401
        # Paths are shown from the generated project's folder on, so a dropped extension or a
        # wrong folder is visible in the log (a cut-off absolute path hid exactly that once).
        shown = []
        for key, value in arguments.items():
            text = str(value)
            if "halcyon_task_eval_" in text:
                text = "…/" + text.split("/weatherline", 1)[-1].lstrip("/")
            shown.append(f"{key}={text[:70]}")
        self.log.append(f"{self.name}({', '.join(shown)})")
        return self.tool.invoke(arguments)


# ----------------------------------------------------------------------------- the tasks


@dataclass(frozen=True)
class Task:
    id: str
    language: str
    prompt: str                                   # {root} is the generated project
    must: tuple[tuple[str, ...], ...]             # every group must match; a group is "any of"
    forbid: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()                   # at least one of these must be called
    what: str = ""                                # what it tests, for the report
    note: str = field(default="", compare=False)


# Ways of saying "it is not there". The first judge knew too few: it failed "cannot be found" and
# "I was unable to find the file", which are right.
NOT_FOUND = ("not found", "does not exist", "doesn't exist", "couldn't find", "could not find", "no such",
             "isn't there", "is not there", "cannot be found", "can't be found", "could not be found",
             "couldn't be found", "unable to find", "can't find", "cannot find", "bulunamadı", "bulamadım",
             "bulunamıyor", "bulunmuyor", "yok", "mevcut değil")

# A number may be written as digits or, as the spoken persona asks, in words; the first judge
# knew only digits and failed "forty-five seconds", which is right.
N8080 = ("8080", "eight thousand eighty", "eighty eighty", "sekiz bin seksen")
N45 = ("45", "forty-five", "forty five", "kırk beş")
N48 = ("48", "forty-eight", "forty eight", "kırk sekiz")
N7 = ("7", "seven", "yedi")
N3 = ("3", "three", "üç")
V34 = ("3.4", "three point four", "üç nokta dört")

# Any of the file tools is a fair way to answer a file task; which one is the model's choice.
FILE_TOOLS = ("list_directory", "read_file", "search_files")

TASKS: tuple[Task, ...] = (
    Task("readme_port", "tr", "{root} klasöründeki README dosyasına göre sunucu varsayılan olarak hangi portta çalışıyor?",
         must=(N8080,), tools=FILE_TOOLS, what="read one named file (Turkish)"),
    Task("yaml_value", "en", "In {root}/config/app.yaml, what is the network timeout?",
         must=(N45,), forbid=("30 seconds", "thirty seconds"), tools=FILE_TOOLS, what="read a config value"),
    Task("find_def", "en", "In the project at {root}, which file defines the function parse_config?",
         must=(("settings",),), tools=FILE_TOOLS, what="find a definition by exploring"),
    Task("deep_constant", "en", "In the project at {root}, where is the maximum number of retries set, and what is it?",
         must=(N7, ("client",)), tools=FILE_TOOLS,
         what="find a value four folders down (more steps than the tool loop allows?)"),
    Task("count_tests", "en", "How many test files are in {root}/tests?",
         must=(N3,), tools=FILE_TOOLS, what="list a folder"),
    Task("bug", "en", "There is a bug in {root}/src/calc.py. What is it?",
         must=(("first", "index 0", "skip", "range(1", "zero"),), tools=FILE_TOOLS,
         what="spot a bug in a short file"),
    Task("bug_tr", "tr", "{root}/src/calc.py dosyasındaki average fonksiyonunda bir hata var. Hata ne?",
         must=(("ilk", "sıfır", "0", "atlı", "range(1", "first"),), tools=FILE_TOOLS,
         what="spot the same bug, asked in Turkish"),
    Task("last_error", "en", "Read {root}/logs/server.log and tell me what the last error was.",
         must=(("quota", "disk"),), forbid=("malformed",), tools=FILE_TOOLS,
         what="the end of a 3000-line file (past the 4000-character cap)"),
    Task("pdf", "en", "What is the maximum input voltage in the specification at {root}/docs/spec.pdf?",
         must=(N48,), tools=FILE_TOOLS, what="a PDF"),
    Task("docx", "tr", "{root}/docs/meeting.docx dosyasına göre toplantı hangi gün?",
         must=(("perşembe", "thursday"),), tools=FILE_TOOLS, what="a Word document (Turkish)"),
    Task("missing", "en", "What is in {root}/src/database.py?",
         must=(NOT_FOUND,), forbid=("def ", "class ", "connect"), tools=FILE_TOOLS,
         what="a file that does not exist: say so, do not invent it"),
    Task("research", "en", "What is the latest release of the Zephyrine Python library, and when did it come out? Say where you found it.",
         must=(V34, ("2026", "september", "two thousand twenty-six")),
         forbid=("latest release is 3.2", "latest version is 3.2"),
         tools=("search_web",), what="research: the answer is on the page, not in the snippets"),
    Task("find_def_tr", "tr", "{root} projesinde parse_config fonksiyonu hangi dosyada tanımlı?",
         must=(("settings",),), tools=FILE_TOOLS, what="find a definition, asked in Turkish"),
    Task("last_error_tr", "tr", "{root}/logs/server.log dosyasındaki en son hata neydi?",
         must=(("quota", "disk", "kota"),), forbid=("malformed",), tools=FILE_TOOLS,
         what="the end of the long log, asked in Turkish"),
    Task("research_tr", "tr", "Zephyrine Python kütüphanesinin en son sürümü hangisi?",
         must=(V34,), forbid=("en son sürümü 3.2", "en son sürümü **3.2"), tools=("search_web",),
         what="the same research, in Turkish"),
)


def judge(task: Task, reply: str, calls: list[str]) -> list[str]:
    from voice.language import guess_language

    text = reply.lower()
    problems = []
    for group in task.must:
        if not any(word.lower() in text for word in group):
            problems.append(f"missing: {' / '.join(group)}")
    for word in task.forbid:
        if word.lower() in text:
            problems.append(f"says: {word}")
    called = {c.split("(")[0] for c in calls}
    if task.tools and not called & set(task.tools):
        problems.append(f"no {' or '.join(task.tools)} call")
    if guess_language(reply, fallback="?") not in (task.language, "?"):
        problems.append("wrong language")
    return problems


# ----------------------------------------------------------------------------- running


def build(model: str | None, deep: bool, spoken: bool = False) -> Any:  # noqa: ANN401
    import core.llm as llm_module
    from core.llm import build_llm, model_capabilities
    from core.modes import DEEP_SYSTEM_TYPED
    from core.profiles import PERFORMANCE
    from core.voice_tools import capability_statement, environment_statement, get_voice_tools

    tools = get_voice_tools()
    profile = PERFORMANCE if model is None else replace(PERFORMANCE, llm_model=model)
    system = None
    if deep:
        # What core/router.py gives deep mode when typing: its persona, the reply budget, the statements.
        profile = replace(profile, llm_num_predict=1500)
        system = DEEP_SYSTEM_TYPED + "\n" + capability_statement(tools) + "\n" + environment_statement()
    llm = build_llm(profile, tools=tools, system=system)
    capabilities = model_capabilities(profile.llm_model)
    if capabilities is not None:
        llm.apply_mode(profile, system=llm.system, use_tools="tools" in capabilities,
                       supports_thinking="thinking" in capabilities)
    # The rounds a typed (or spoken) turn gets, where the code under test has the setting.
    rounds = getattr(llm_module, "SPOKEN_TOOL_ROUNDS" if spoken else "TYPED_TOOL_ROUNDS", None)
    if rounds is not None and hasattr(llm, "max_tool_rounds"):
        llm.max_tool_rounds = rounds
    return llm


def run(model: str | None, deep: bool, only: set[str] | None, seed: int = 7,
        spoken: bool = False) -> list[tuple[Task, list[str]]]:
    from core.llm import stream_reply

    llm = build(model, deep, spoken)
    llm._options["seed"] = seed
    rounds = getattr(llm, "max_tool_rounds", 4)
    print(f"\n########## {llm.model}  ({'deep-mode prompt' if deep else 'general prompt'}, "
          f"context {llm.profile.llm_num_ctx}, reply cap {llm.profile.llm_num_predict}, "
          f"{rounds} tool rounds, seed {seed})", flush=True)
    llm.warmup()
    raw_stream = llm._raw_stream
    workdir = Path(tempfile.mkdtemp(prefix="halcyon_task_eval_"))
    results = []
    try:
        root = workdir / "weatherline"
        build_project(root)
        for task in TASKS:
            if only and task.id not in only:
                continue
            calls: list[str] = []
            for name, tool in list(llm._tools.items()):
                base = tool.tool if isinstance(tool, Recorder) else tool
                if name == "search_web":
                    base = FakeSearch()
                elif name == "fetch_webpage":
                    base = FakeFetch()
                llm._tools[name] = Recorder(base, calls)
            llm.reset()
            prompt = task.prompt.format(root=root.as_posix())
            rounds = [0]
            def counted(*args, _inner=raw_stream, **kwargs):
                if kwargs.get("num_predict") is None:     # a generation for the turn, not a wake-up
                    rounds[0] += 1
                return _inner(*args, **kwargs)
            llm._raw_stream = counted
            started = time.perf_counter()
            try:
                reply = "".join(stream_reply(llm, prompt, language=task.language)).strip()
            except Exception as exc:  # noqa: BLE001
                reply = f"(error: {exc})"
            seconds = time.perf_counter() - started
            problems = judge(task, reply, calls)
            results.append((task, problems))
            verdict = "PASS" if not problems else "FAIL"
            flat = re.sub(r"\s+", " ", reply)[:3000]
            used = " -> ".join(calls) or "none"
            print(f"\n[{verdict}] {task.id} - {task.what}  ({seconds:.1f} s, {rounds[0]} rounds)\n  tools: {used}\n  reply: {flat}"
                  + (f"\n  problems: {'; '.join(problems)}" if problems else ""), flush=True)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    passed = sum(1 for _, problems in results if not problems)
    print(f"\n=> {llm.model} seed {seed}: {passed}/{len(results)} passed", flush=True)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default=None, help="the general model to test (default: the 8 GB profile's)")
    parser.add_argument("--deep", default=None, metavar="MODEL", help="test MODEL with the deep-mode prompt instead")
    parser.add_argument("--only", default="", help="comma-separated task ids")
    parser.add_argument("--seeds", default="7", help="comma-separated seeds; one full run per seed")
    parser.add_argument("--spoken", action="store_true", help="give each turn the rounds a spoken turn gets")
    parser.add_argument("--rescore", default=None, metavar="LOG",
                        help="judge the replies in a saved log again with the current rules; nothing is run")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.rescore:
        rescore(Path(args.rescore))
        return 0
    only = {x.strip() for x in args.only.split(",") if x.strip()} or None
    seeds = [int(x) for x in args.seeds.split(",") if x.strip()]
    tally: dict[str, list[bool]] = {}
    order: list[Task] = []
    for seed in seeds:
        for task, problems in run(args.deep or args.model, bool(args.deep), only, seed, args.spoken):
            if task.id not in tally:
                order.append(task)
            tally.setdefault(task.id, []).append(not problems)
    total = sum(sum(v) for v in tally.values())
    print(f"\n========== summary over {len(seeds)} seed{'s' if len(seeds) != 1 else ''}: "
          f"{total}/{len(seeds) * len(order)} task runs passed")
    for task in order:
        wins = tally[task.id]
        print(f"  {task.id:14s} {sum(wins)}/{len(wins)}  {task.what}")
    _unload(args.deep or args.model)
    return 0


def rescore(log: Path) -> None:
    """
    Judge the replies of a saved run again with the current rules, so two runs made at different
    times can be compared under one judge. Replies logged before full replies were kept are cut
    at 500 characters; the facts asked for came well before that in every reply read by hand.
    """
    tasks = {task.id: task for task in TASKS}
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    tally: dict[str, list[bool]] = {}
    per_seed: dict[str, list[bool]] = {}
    model, seed = "?", "?"
    for i, line in enumerate(lines):
        header = re.match(r"^#{10} (\S+) .*seed (\d+)\)", line)
        if header:
            model, seed = header.group(1), header.group(2)
            continue
        result = re.match(r"^\[(?:PASS|FAIL)\] (\S+) - ", line)
        if not result or result.group(1) not in tasks or i + 2 >= len(lines):
            continue
        used = lines[i + 1].split("tools:", 1)[-1].strip()
        calls = [] if used == "none" else [c.strip() for c in used.split(" -> ")]
        reply = lines[i + 2].split("reply:", 1)[-1].strip()
        passed = not judge(tasks[result.group(1)], reply, calls)
        tally.setdefault(result.group(1), []).append(passed)
        per_seed.setdefault(seed, []).append(passed)
    print(f"{log.name}: {model}, rescored with the current rules")
    for seed_name, results in per_seed.items():
        print(f"  seed {seed_name}: {sum(results)}/{len(results)}")
    total = sum(sum(v) for v in tally.values())
    print(f"  all: {total}/{sum(len(v) for v in tally.values())} task runs passed")
    for task in TASKS:
        if task.id in tally:
            wins = tally[task.id]
            print(f"  {task.id:14s} {sum(wins)}/{len(wins)}  {task.what}")


def _unload(model: str | None) -> None:
    """Free the card for whatever runs next (a 26B model that cannot load is the alternative)."""
    try:
        from core.llm import build_llm
        from core.profiles import PERFORMANCE

        profile = PERFORMANCE if model is None else replace(PERFORMANCE, llm_model=model)
        build_llm(profile).unload()
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    sys.exit(main())
