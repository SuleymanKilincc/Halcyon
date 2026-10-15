"""
Tests for the sentence splitter and the speech text cleaner (voice/tts.py).

The splitter decides when the first sentence of an answer is handed to the
speech synthesiser, so it directly sets how soon Halcyon starts talking. A bug
here does not crash anything - it just makes the assistant silently slower or
makes it read fragments, which is exactly the kind of regression only a test
catches.
"""

from voice.tts import SentenceStreamer, clean_for_speech


def feed(streamer: SentenceStreamer, deltas: list[str]) -> list[str]:
    """Push deltas the way the LLM stream does and collect released sentences."""
    released: list[str] = []
    for delta in deltas:
        released.extend(streamer.push(delta))
    return released


def test_releases_a_sentence_as_soon_as_it_is_complete():
    s = SentenceStreamer(min_chars=12)
    assert feed(s, ["I created the file and wrote to it. ", "Anything"]) == [
        "I created the file and wrote to it."
    ]


def test_does_not_release_an_unfinished_sentence():
    s = SentenceStreamer(min_chars=12)
    assert feed(s, ["I created the file", " and wrote"]) == []


def test_short_opener_is_merged_into_the_next_sentence():
    # "Sure." alone sounds clipped when spoken, so it rides along with the
    # next sentence instead of being synthesised on its own.
    s = SentenceStreamer(min_chars=12)
    released = feed(s, ["Sure. ", "I created the file. ", "Next"])
    assert released == ["Sure. I created the file."]


def test_decimal_number_is_not_treated_as_a_sentence_end():
    s = SentenceStreamer(min_chars=12)
    released = feed(s, ["The model takes 3.5 GB of memory. ", "Shall we continue? "])
    assert released == ["The model takes 3.5 GB of memory.", "Shall we continue?"]


def test_flush_returns_whatever_is_left():
    s = SentenceStreamer(min_chars=12)
    feed(s, ["Done."])
    assert s.flush() == ["Done."]
    assert s.flush() == []  # and the buffer is empty afterwards


def test_question_and_exclamation_marks_end_sentences():
    s = SentenceStreamer(min_chars=5)
    assert feed(s, ["Are you ready? Here we go! ", "x"]) == ["Are you ready?", "Here we go!"]


def test_turkish_text_is_split_with_its_characters_intact():
    # Halcyon speaks Turkish, so the splitter must handle Turkish letters and
    # punctuation. The input is Turkish on purpose: it is the data under test.
    s = SentenceStreamer(min_chars=5)
    assert feed(s, ["Hazır mısın? Başlıyoruz! ", "x"]) == ["Hazır mısın?", "Başlıyoruz!"]


def test_clean_for_speech_strips_markdown_emphasis():
    assert clean_for_speech("**Done**, sir") == "Done, sir"


def test_clean_for_speech_replaces_code_blocks_and_urls():
    text = "Look at this: ```print('x')``` and https://example.com/a?b=c here."
    cleaned = clean_for_speech(text)
    assert "print" not in cleaned
    assert "https://" not in cleaned
    assert "code block" in cleaned
    assert "link" in cleaned


def test_spoken_placeholders_follow_the_reply_language():
    # What replaces a URL is spoken aloud, so a Turkish reply must not suddenly
    # say an English word in the middle of it.
    assert "bağlantı" in clean_for_speech("https://example.com", language="tr")
    assert "link" in clean_for_speech("https://example.com", language="en")


def test_clean_for_speech_keeps_inline_code_text_without_backticks():
    assert clean_for_speech("run `build now` first") == "run build now first"
    # A file name inside backticks is then spoken like any other file name.
    assert clean_for_speech("open `config.py` now") == "open config now"


def test_clean_for_speech_collapses_whitespace():
    assert clean_for_speech("  one   two \n three  ") == "one two three"


# ------------------------------------------------ file names are spoken as words

def test_names_with_underscores_are_spoken_as_separate_words():
    # "meeting_notes" was cleaned to "meetingnotes": one unpronounceable word.
    assert clean_for_speech("Read meeting_notes please") == "Read meeting notes please"


def test_the_extension_is_not_spelled_out():
    # "hello dot p y" was measured 20-30% faster than ordinary speech and mumbled.
    assert clean_for_speech("It is hello.py") == "It is hello"
    assert clean_for_speech("Open notes.txt now") == "Open notes now"


def test_a_snake_case_file_name_is_spoken_as_words():
    text = "The files are alisveris_listesi.txt, hello.py, and meeting_notes.txt."
    assert clean_for_speech(text) == "The files are alisveris listesi, hello, and meeting notes."


def test_a_file_name_in_a_turkish_reply_is_spoken_the_same_way():
    assert clean_for_speech("Dosya notlar.txt", "tr") == "Dosya notlar"


def test_numbers_with_a_decimal_point_and_ordinary_sentences_are_untouched():
    assert clean_for_speech("It needs 3.5 GB. Then it stops.") == "It needs 3.5 GB. Then it stops."
    assert clean_for_speech("Version 3.13 is out.") == "Version 3.13 is out."


# ------------------------------------------------ closing offers are not read aloud

import pytest  # noqa: E402

from voice.tts import is_closing_offer  # noqa: E402


@pytest.mark.parametrize("sentence", [
    "Would you like me to read any of them?",
    "Do you want me to explain how it works?",
    "Is there anything specific you'd like me to do next?",
    "Let me know if you need anything else.",
    "Shall I open it?",
    "Başka bir şey okumamı ister misin?",
    "İsterseniz dosyayı da okuyabilirim.",     # capital İ lowercases with a combining dot
    "İster misin okuyayım?",
])
def test_closing_offers_are_recognised(sentence):
    assert is_closing_offer(sentence)


@pytest.mark.parametrize("sentence", [
    "The demo folder contains three files.",
    "I can list the contents of your Projects folder instead.",
    "I cannot delete files yet.",
    "Which folder do you mean?",
    "Shallow water is cold.",
    "Istanbul is big.",
    "Dosyada üç satır var.",
])
def test_real_answers_and_questions_are_not_mistaken_for_offers(sentence):
    assert not is_closing_offer(sentence)
