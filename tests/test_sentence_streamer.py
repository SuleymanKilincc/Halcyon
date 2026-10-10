"""
Tests for the sentence splitter and the speech text cleaner (voice/tts.py).

The splitter decides when the first sentence of an answer is handed to the
speech synthesiser, so it directly sets how soon Jarvis starts talking. A bug
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
    # Jarvis speaks Turkish, so the splitter must handle Turkish letters and
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
    assert clean_for_speech("open `config.py` now") == "open config.py now"


def test_clean_for_speech_collapses_whitespace():
    assert clean_for_speech("  one   two \n three  ") == "one two three"
