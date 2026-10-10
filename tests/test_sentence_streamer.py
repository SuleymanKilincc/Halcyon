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
    assert feed(s, ["Dosyayı oluşturdum ve içine yazdım. ", "Başka"]) == [
        "Dosyayı oluşturdum ve içine yazdım."
    ]


def test_does_not_release_an_unfinished_sentence():
    s = SentenceStreamer(min_chars=12)
    assert feed(s, ["Dosyayı oluşturdum", " ve içine"]) == []


def test_short_opener_is_merged_into_the_next_sentence():
    # "Tabii." alone sounds clipped when spoken, so it rides along with the
    # next sentence instead of being synthesised on its own.
    s = SentenceStreamer(min_chars=12)
    released = feed(s, ["Tabii. ", "Dosyayı oluşturdum. ", "Devam"])
    assert released == ["Tabii. Dosyayı oluşturdum."]


def test_decimal_number_is_not_treated_as_a_sentence_end():
    s = SentenceStreamer(min_chars=12)
    released = feed(s, ["Model 3.5 GB yer kaplıyor. ", "Devam edelim mi? "])
    assert released == ["Model 3.5 GB yer kaplıyor.", "Devam edelim mi?"]


def test_flush_returns_whatever_is_left():
    s = SentenceStreamer(min_chars=12)
    feed(s, ["Tamam."])
    assert s.flush() == ["Tamam."]
    assert s.flush() == []  # and the buffer is empty afterwards


def test_question_and_exclamation_marks_end_sentences():
    s = SentenceStreamer(min_chars=5)
    assert feed(s, ["Hazır mısın? Başlıyoruz! ", "x"]) == ["Hazır mısın?", "Başlıyoruz!"]


def test_clean_for_speech_strips_markdown_emphasis():
    assert clean_for_speech("**Tamam** efendim") == "Tamam efendim"


def test_clean_for_speech_replaces_code_blocks_and_urls():
    text = "Şuna bak: ```print('x')``` ve https://example.com/a?b=c adresi."
    cleaned = clean_for_speech(text)
    assert "print" not in cleaned
    assert "https://" not in cleaned
    assert "kod bloğu" in cleaned
    assert "bağlantı" in cleaned


def test_clean_for_speech_keeps_inline_code_text_without_backticks():
    assert clean_for_speech("`config.py` dosyasını aç") == "config.py dosyasını aç"


def test_clean_for_speech_collapses_whitespace():
    assert clean_for_speech("  bir   iki \n üç  ") == "bir iki üç"
