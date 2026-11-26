"""
Tests for reading, searching and listing files (core/files.py), the logic behind the file tools.

Each group is a failure that bench/task_eval.py measured with the old tools: the end of a long
log out of reach, PDF and Word files read as raw bytes, a definition that took more rounds to
find than the tool loop allowed, and a name given without its extension reported as missing.
Everything runs on small files made in a temporary folder, plus one committed PDF (making a PDF
needs a library the test environment does not have; reading one needs only pypdf).
"""

from pathlib import Path

import pytest

from core import files
from core.files import listing, read_window, resolve, search

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "weatherline"
    (root / "src" / "app" / "network").mkdir(parents=True)
    (root / "logs").mkdir()
    (root / "node_modules" / "pkg").mkdir(parents=True)
    (root / "README.md").write_text("# Weatherline\nThe server listens on port 8080.\n", encoding="utf-8")
    (root / "src" / "app" / "settings.py").write_text("def parse_config(path):\n    return {}\n", encoding="utf-8")
    (root / "src" / "app" / "network" / "client.py").write_text("MAX_RETRIES = 7\n", encoding="utf-8")
    (root / "node_modules" / "pkg" / "index.js").write_text("// MAX_RETRIES = 99\n", encoding="utf-8")
    log = [f"2026-11-20 INFO reading {i}" for i in range(3000)]
    log[412] = "2026-11-20 ERROR station 17 sent a malformed reading"
    log[2950] = "2026-11-20 ERROR disk quota exceeded"
    (root / "logs" / "server.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    return root


# ------------------------------------------------------------------------------ names

def test_a_name_without_its_extension_finds_the_one_file_it_can_mean(project):
    """Two models asked for README when the file was README.md, and were told it did not exist."""
    path, note = resolve((project / "README").as_posix(), project)
    assert path == project / "README.md"
    assert "README.md" in note and "only name there that matches" in note


def test_a_name_in_the_wrong_case_is_found(project):
    # Windows opens it as written; on Linux and in CI the name has to be matched.
    path, _ = resolve((project / "readme.MD").as_posix(), project)
    assert path is not None and path.name.lower() == "readme.md"
    assert "port 8080" in read_window(path)


def test_an_ambiguous_name_is_not_guessed(project):
    (project / "README.txt").write_text("other", encoding="utf-8")
    path, message = resolve((project / "README").as_posix(), project)
    assert path is None and "README.md" in message and "README.txt" in message


def test_a_missing_file_says_what_the_folder_does_contain(project):
    path, message = resolve((project / "src" / "database.py").as_posix(), project)
    assert path is None
    assert "database.py" in message and "app/" in message


def test_a_missing_folder_is_named_with_the_nearest_folder_that_exists(project):
    path, message = resolve((project / "source" / "calc.py").as_posix(), project)
    assert path is None
    assert "no folder 'source'" in message and "src/" in message


def test_a_folder_given_where_a_file_is_wanted_says_so(project):
    path, message = resolve((project / "src").as_posix(), project, want="file")
    assert path is None and "is a folder" in message


def test_a_relative_path_is_taken_from_the_base(project):
    path, _ = resolve("README.md", project)
    assert path == project / "README.md"


# ------------------------------------------------------------------------------ reading

def test_a_small_file_is_read_whole_with_line_numbers(project):
    text = read_window(project / "README.md")
    assert "2 lines" in text and "2| The server listens on port 8080." in text
    assert "Another part" not in text


def test_a_long_file_comes_back_as_a_window_that_fits_and_says_how_to_continue(project):
    text = read_window(project / "logs" / "server.log")
    assert len(text) <= files.WINDOW_CHARS
    assert text.startswith("server.log") and "lines 1-" in text and "of 3000" in text
    assert "start_line" in text


def test_the_end_of_a_long_log_is_reachable(project):
    """The last error of a 3000-line log sat at character 164,000; the old tool showed the first 4000."""
    text = read_window(project / "logs" / "server.log", start_line=-60)
    assert "2951| 2026-11-20 ERROR disk quota exceeded" in text
    assert "3000| 2026-11-20 INFO reading 2999" in text


def test_reading_from_a_given_line(project):
    text = read_window(project / "logs" / "server.log", start_line=410, end_line=415)
    assert "lines 410-415 of 3000" in text and "413| 2026-11-20 ERROR station 17" in text


def test_a_start_past_the_end_is_said(project):
    assert "past the end" in read_window(project / "README.md", start_line=50)


def test_a_line_that_is_too_long_is_cut(tmp_path):
    path = tmp_path / "min.js"
    path.write_text("x" * 5000 + "\n", encoding="utf-8")
    text = read_window(path)
    assert "characters]" in text and len(text) < 1000


def test_a_binary_file_is_not_dumped(tmp_path):
    path = tmp_path / "blob.dat"
    path.write_bytes(b"\x00\x01\x02" * 1000)
    assert "not a text file" in read_window(path)


def test_an_empty_file_is_said_to_be_empty(tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")
    assert "is empty" in read_window(path)


def test_a_turkish_windows_file_is_read_without_mojibake(tmp_path):
    path = tmp_path / "notlar.txt"
    path.write_bytes("Toplantı Perşembe günü, ağaç ve ışık.\n".encode("cp1254"))
    assert "Toplantı Perşembe günü, ağaç ve ışık." in read_window(path)


def test_a_pdf_is_read_as_its_text_page_by_page():
    """Read through the old tool, this PDF was compressed bytes: the text is not in the file as written."""
    raw = (FIXTURES / "spec.pdf").read_bytes()
    assert b"Maximum input voltage" not in raw
    text = read_window(FIXTURES / "spec.pdf")
    assert "PDF, 2 pages" in text
    assert "--- page 1 ---" in text and "Maximum input voltage: 48 V." in text
    assert "--- page 2 ---" in text


def test_a_word_document_is_read_in_order_with_its_tables(tmp_path):
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_paragraph("Ekip toplantısı her hafta Perşembe saat 14:00'te yapılır.")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "İstasyon", "Durum"
    table.cell(1, 0).text, table.cell(1, 1).text = "17", "bozuk"
    document.add_paragraph("Son paragraf.")
    path = tmp_path / "meeting.docx"
    document.save(str(path))
    text = read_window(path)
    assert "Word document" in text
    lines = [line.split("| ", 1)[1] for line in text.splitlines()[1:]]
    assert lines == ["Ekip toplantısı her hafta Perşembe saat 14:00'te yapılır.", "İstasyon | Durum",
                     "17 | bozuk", "Son paragraf."]


def test_a_broken_document_is_reported_not_raised(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.4 this is not really a pdf")
    assert "could not be read" in read_window(path) or "no text" in read_window(path)


# ------------------------------------------------------------------------------ searching

def test_the_errors_of_a_log_are_found_in_one_call(project):
    text = search("error", project / "logs" / "server.log")
    assert text.startswith('2 lines contain "error" in server.log')
    assert "server.log:413:" in text and "server.log:2951: 2026-11-20 ERROR disk quota exceeded" in text


def test_a_definition_is_found_in_a_folder_tree(project):
    text = search("def parse_config", project)
    assert "src/app/settings.py:1: def parse_config(path):" in text


def test_underscores_and_case_do_not_matter(project):
    text = search("max retries", project)
    assert "src/app/network/client.py:1: MAX_RETRIES = 7" in text


def test_folders_that_are_never_meant_are_skipped(project):
    assert "node_modules" not in search("MAX_RETRIES", project)


def test_when_nothing_matches_exactly_the_closest_lines_are_offered_and_called_closest(project):
    text = search("maximum number of retries", project)
    assert "No line contains" in text and "closest" in text
    assert "MAX_RETRIES = 7" in text


def test_many_matches_in_one_file_keep_the_first_and_the_last(project):
    """The last error of a log matters as much as the first, so a long list is cut in the middle."""
    text = search("INFO", project / "logs" / "server.log")
    assert "server.log:1:" in text and "server.log:3000:" in text and "more in between" in text
    assert len(text) <= files.WINDOW_CHARS


def test_a_pdf_is_searched_too(tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "spec.pdf").write_bytes((FIXTURES / "spec.pdf").read_bytes())
    assert "spec.pdf:3: Supply: 12 to 48 V DC. Maximum input voltage: 48 V." in search("voltage", folder)


def test_nothing_found_is_said_plainly(project):
    assert search("zeppelin", project).startswith('No line contains "zeppelin"')


def test_an_empty_query_is_refused(project):
    assert "Nothing to search for" in search("  ", project)


# ------------------------------------------------------------------------------ listing

def test_a_listing_shows_folders_first_with_counts_and_file_sizes(project):
    text = listing(project)
    lines = text.splitlines()
    assert lines[0].endswith("weatherline/")
    assert lines[1].strip().startswith("logs/") and "(1 item)" in lines[1]
    assert any(line.strip().startswith("README.md") and line.strip().endswith("B") for line in lines)


def test_a_deeper_listing_shows_a_whole_project_in_one_call(project):
    text = listing(project, depth=4)
    assert "      network/" in text and "        client.py" in text
    assert "node_modules/  (1 item)" in text           # shown, but not walked into


def test_an_empty_folder_says_so(tmp_path):
    assert "(empty)" in listing(tmp_path)


def test_a_huge_folder_is_cut_to_fit_and_says_how_much_is_hidden(tmp_path):
    for i in range(500):
        (tmp_path / f"file_{i:03d}.txt").write_text("x", encoding="utf-8")
    text = listing(tmp_path)
    assert len(text) <= files.WINDOW_CHARS and "more entries not shown" in text
