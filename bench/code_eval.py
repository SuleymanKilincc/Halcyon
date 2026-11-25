"""
Can a model write correct code? Used to choose the models behind deep mode (docs/MODES.md).

    python -m bench.code_eval --set easy gemma4:26b-a4b qwen3.5:9b
    python -m bench.code_eval --set hard --max-tokens 3000 gemma4:e4b
    python -m bench.code_eval --set hard --think mimo-v2.6:9b     # let a thinking model think
    python -m bench.code_eval --check                             # test the tests (no model needed)

Each task asks for one Python function or class. The code block of the reply is run
against hidden asserts in a separate interpreter (isolated mode, a temporary directory,
10 s limit) and counts as passed only if every assert holds. Reports pass/fail per task,
generation speed and the placement Ollama chose (how much of the model sits on the GPU).

What keeps the comparison fair, and what it cannot tell you:

* Every model gets the same prompts, the same seed and the same options; thinking is
  switched off for models that support it unless --think is given, so the comparison is
  about the answer and not about how long a model may ponder.
* Every task ships with a reference solution (bench/code_tasks/*.json) and `--check`
  runs the hidden asserts against it, so a failing model cannot be blamed on a broken
  test. tests/test_bench_code_eval.py does the same on every test run.
* A reply cut off at --max-tokens fails with a SyntaxError. The log shows the token count,
  so truncation can be told apart from a wrong answer; re-run with a larger cap to separate them.
* It is one run per model and eight tasks per set: a one-task difference is noise.
  Models that fail in many different ways cannot be ranked by it, only grouped.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

OLLAMA = "http://127.0.0.1:11434"
TASK_DIR = Path(__file__).parent / "code_tasks"
SUFFIX = "\n\nReply with the code in one python code block and nothing else."
TIMEOUT_S = 10


def load_tasks(name: str) -> list[dict[str, str]]:
    """The tasks of one set: id, prompt, hidden asserts and a reference solution."""
    return json.loads((TASK_DIR / f"{name}.json").read_text(encoding="utf-8"))


def extract_code(reply: str) -> str:
    """The longest fenced block of the reply, or the whole reply when it has none."""
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", reply, re.S)
    return max(blocks, key=len) if blocks else reply


def run_tests(code: str, tests: str) -> tuple[bool, str]:
    """Run `code` followed by the hidden asserts in a fresh interpreter; (passed, last error line)."""
    with tempfile.TemporaryDirectory() as directory:
        script = Path(directory) / "attempt.py"
        script.write_text(code + "\n\n" + tests + "\nprint('OK')\n", encoding="utf-8")
        try:
            done = subprocess.run([sys.executable, "-I", str(script)], capture_output=True, text=True,
                                  timeout=TIMEOUT_S, cwd=directory)
        except subprocess.TimeoutExpired:
            return False, "timeout"
    passed = done.returncode == 0 and "OK" in done.stdout
    return passed, "" if passed else (done.stderr.strip().splitlines() or ["failed"])[-1][:120]


def run_all(attempts: list[tuple[str, str]]) -> list[tuple[bool, str]]:
    """run_tests for several (code, tests) pairs at once; each runs in its own interpreter."""
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(lambda pair: run_tests(*pair), attempts))


def check_references(name: str) -> list[str]:
    """Ids of tasks whose reference solution does NOT pass its own tests (should be none)."""
    tasks = load_tasks(name)
    results = run_all([(task["reference"], task["tests"]) for task in tasks])
    return [task["id"] for task, (passed, _) in zip(tasks, results) if not passed]


# ----------------------------------------------------------------------------- Ollama


def _post(path: str, body: dict, timeout: int = 1800) -> dict:
    request = urllib.request.Request(OLLAMA + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def _capabilities(model: str) -> list[str]:
    try:
        return _post("/api/show", {"model": model}, 30).get("capabilities", [])
    except Exception:  # noqa: BLE001
        return []


def _unload(model: str) -> None:
    try:
        _post("/api/generate", {"model": model, "keep_alive": 0}, 60)
    except Exception:  # noqa: BLE001
        pass


def _placement() -> str:
    out = subprocess.run(["ollama", "ps"], capture_output=True, text=True).stdout.strip().splitlines()
    return out[1] if len(out) > 1 else "(not loaded)"


def evaluate(model: str, tasks: list[dict[str, str]], *, max_tokens: int, think: bool) -> int:
    capabilities = _capabilities(model)
    print(f"\n##### {model}  capabilities={capabilities}", flush=True)
    _unload(model)
    speeds: list[float] = []
    passed = 0
    for task in tasks:
        context = 10240 if think else 4096
        body = {"model": model, "stream": False, "keep_alive": "5m",
                "messages": [{"role": "user", "content": task["prompt"] + SUFFIX}],
                "options": {"temperature": 0.2, "seed": 7, "num_ctx": context,
                            "num_predict": 7000 if think else max_tokens}}
        if "thinking" in capabilities:
            body["think"] = think
        started = time.perf_counter()
        try:
            result = _post("/api/chat", body)
        except Exception as exc:  # noqa: BLE001
            print(f"  {task['id']:10s} ERROR {exc}", flush=True)
            continue
        wall = time.perf_counter() - started
        ok, why = run_tests(extract_code(result["message"]["content"]), task["tests"])
        tokens, seconds = result.get("eval_count", 0), result.get("eval_duration", 1) / 1e9
        if tokens > 20:
            speeds.append(tokens / seconds)
        passed += ok
        print(f"  {task['id']:10s} {'PASS' if ok else 'FAIL'}  {tokens:5d} tok  {tokens / seconds:6.1f} tok/s  "
              f"wall {wall:6.1f}s  {why}", flush=True)
    median = sorted(speeds)[len(speeds) // 2] if speeds else 0.0
    print(f"  => {passed}/{len(tasks)} passed | median speed {median:.1f} tok/s | {_placement()}", flush=True)
    _unload(model)
    return passed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("models", nargs="*", help="Ollama model names")
    parser.add_argument("--set", dest="task_set", choices=("easy", "hard"), default="easy")
    parser.add_argument("--max-tokens", type=int, default=1200, help="reply cap (default 1200)")
    parser.add_argument("--think", action="store_true", help="let thinking models think (cap raised to 7000)")
    parser.add_argument("--check", action="store_true", help="run the hidden asserts against the reference solutions")
    args = parser.parse_args()

    if args.check:
        bad = {name: check_references(name) for name in ("easy", "hard")}
        for name, ids in bad.items():
            print(f"{name}: {'all references pass' if not ids else 'REFERENCE FAILS: ' + ', '.join(ids)}")
        return 1 if any(bad.values()) else 0
    if not args.models:
        parser.error("name at least one model, or use --check")
    tasks = load_tasks(args.task_set)
    for model in args.models:
        evaluate(model, tasks, max_tokens=args.max_tokens, think=args.think)
    return 0


if __name__ == "__main__":
    sys.exit(main())
