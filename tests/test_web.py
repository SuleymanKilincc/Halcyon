"""
Tests for what the web tools give the model (core/web.py): search results it can follow, and the
part of a page it needs. Measured before: the search returned snippet text without links, so the
model could not open the page behind a snippet, and answered from an out-of-date snippet or not
at all.
"""

from core.files import WINDOW_CHARS
from core.web import format_search_results, page_view

RESULTS = [
    {"title": "Releases - Zephyrine", "href": "https://zephyrine.dev/releases", "body": "Release notes."},
    {"title": "zephyrine - PyPI", "link": "https://pypi.org/project/zephyrine/", "snippet": "pip install zephyrine"},
]


def test_every_result_carries_its_link_so_the_page_can_be_opened():
    text = format_search_results("zephyrine latest", RESULTS)
    assert "1. Releases - Zephyrine\n   https://zephyrine.dev/releases\n   Release notes." in text
    assert "https://pypi.org/project/zephyrine/" in text           # other key names are understood too
    assert "fetch_webpage" in text and "out of date" in text


def test_no_results_suggests_other_words():
    assert "Try other words" in format_search_results("qwxyz", [])


def test_a_long_snippet_is_cut():
    text = format_search_results("q", [{"title": "t", "href": "https://x", "body": "word " * 200}])
    assert "..." in text and len(text) < 800


PAGE = "\n".join(["Zephyrine releases", "3.4.0 (2026-09-02): latest release.", "3.3.1 (2026-06-14): bug fixes.",
                  *[f"filler line {i} about nothing in particular" for i in range(400)],
                  "Appendix: the maximum batch size is 512."])


def test_a_long_page_gives_its_start_and_says_how_to_reach_the_rest():
    text = page_view("https://zephyrine.dev/releases", PAGE)
    assert text.startswith("Content from https://zephyrine.dev/releases (the first")
    assert "3.4.0 (2026-09-02)" in text and "find=" in text
    assert len(text) <= WINDOW_CHARS


def test_find_reaches_a_fact_far_down_the_page_with_its_neighbours():
    text = page_view("https://zephyrine.dev/releases", PAGE, find="batch size")
    assert '1 part mentions "batch size"' in text
    assert "the maximum batch size is 512" in text
    assert "filler line 399" in text                               # the line before it, for context


def test_find_that_does_not_appear_says_so_and_gives_the_start():
    text = page_view("https://example.com", PAGE, find="zeppelin")
    assert text.startswith('"zeppelin" does not appear on https://example.com') and "Zephyrine releases" in text


def test_a_short_page_is_given_whole():
    assert page_view("https://x", "one\n\n two  words ") == "Content from https://x:\none\ntwo words"


def test_an_empty_page_is_said_to_be_empty():
    assert "no readable text" in page_view("https://x", "  \n ")
