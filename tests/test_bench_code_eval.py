"""
Tests for the code benchmark's own machinery (bench/code_eval.py), not for any model.

A benchmark is only worth quoting if a failing score cannot be the test's fault. So every
task ships a reference solution and these tests run it against the task's hidden asserts;
they also check that the asserts are not vacuous (a wrong answer must fail) and that
the harness copes with the ways a model reply goes wrong.
"""

import pytest

from bench.code_eval import check_references, extract_code, load_tasks, run_all, run_tests

SETS = ("easy", "hard")


@pytest.mark.parametrize("name", SETS)
def test_every_reference_solution_passes_its_own_hidden_asserts(name):
    assert check_references(name) == []


@pytest.mark.parametrize("name", SETS)
def test_task_ids_are_unique_and_every_task_is_complete(name):
    tasks = load_tasks(name)
    assert len({task["id"] for task in tasks}) == len(tasks) == 8
    for task in tasks:
        assert task["prompt"] and task["tests"] and task["reference"], task["id"]


@pytest.mark.parametrize("name", SETS)
def test_the_asserts_are_not_vacuous_an_empty_answer_fails_every_task(name):
    tasks = load_tasks(name)
    for task, (passed, _) in zip(tasks, run_all([("", task["tests"]) for task in tasks])):
        assert passed is False, task["id"]


def test_the_original_bug_in_the_repair_tasks_is_caught_by_their_asserts(monkeypatch):
    """The broken code shown in the prompt must fail, otherwise the task would test nothing."""
    import bench.code_eval as code_eval

    monkeypatch.setattr(code_eval, "TIMEOUT_S", 2)    # the broken binary search loops forever; that is a failure too
    for name, task_id, marker in (("easy", "bugfix", "def binary_search"), ("hard", "ratelimit", "class RateLimiter")):
        task = next(t for t in load_tasks(name) if t["id"] == task_id)
        broken = extract_code(task["prompt"])
        assert marker in broken
        assert run_tests(broken, task["tests"])[0] is False, task_id


def test_a_wrong_answer_is_reported_with_its_error_line():
    passed, why = run_tests("def f():\n    return 1\n", "assert f() == 2")
    assert passed is False and "AssertionError" in why


def test_a_reply_that_never_ends_is_stopped_not_waited_for(monkeypatch):
    import bench.code_eval as code_eval

    monkeypatch.setattr(code_eval, "TIMEOUT_S", 1)
    assert run_tests("while True:\n    pass\n", "pass") == (False, "timeout")


def test_a_reply_cut_off_in_the_middle_fails_cleanly():
    passed, why = run_tests("def f(:\n", "assert True")
    assert passed is False and "SyntaxError" in why


def test_the_longest_code_block_is_taken_and_a_reply_without_a_fence_is_used_whole():
    reply = "Here:\n```python\nx = 1\n```\nand better:\n```python\nx = 1\ny = 2\n```\n"
    assert extract_code(reply).strip() == "x = 1\ny = 2"
    assert extract_code("x = 3") == "x = 3"
