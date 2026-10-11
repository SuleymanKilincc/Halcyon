"""
Tests for choosing the reply voice by the language of the text (voice/language.py).

Most English cases are verbatim replies and requests from a real session - the
one in which an English reply was read out by the Turkish voice. The Turkish
cases include sentences with no Turkish-specific letters, and Turkish
sentences carrying English technical terms, which are the hard ones.
"""

import pytest

from voice.language import guess_language

ENGLISH = [
    # Halcyon's replies in a real session
    "I am functioning well, sir. How may I assist you today?",
    "Your desktop contains several application shortcuts, including Steam and Chrome.",
    "That path does not exist, sir.",
    "Would you like me to check the root of your C drive or another specific folder?",
    "I see twelve project folders, sir.",
    "They include Jarvis, optik_otomasyon, and several others like SuleymanKilincc.github.io-main.",
    "I cannot create folders directly, sir.",
    "The TuneShop.Core folder contains a project file and several subfolders.",
    # the user's requests in the same session
    "Hi Jarvis, how are you?",
    "Check my desktop folders",
    "Go inside Desktop and say what you think.",
    # hard: Turkish names or paths inside English
    "Hello Süleyman, how are you today?",
    "The folder is at C:/Users/Asus/Desktop/PROJELERİM.",
    # short
    "Yes, sir.",
    "Done.",
]

TURKISH = [
    "Masaüstündeki klasörleri listeler misin",
    "Bilgisayarımın sıcaklığı kaç derece",
    "Göreviniz nedir efendim?",
    "Efendim, masaüstünüzde on bir klasör var.",
    # no Turkish-specific letters at all
    "Tamam efendim.",
    "Bu klasorde ne var?",
    "Evet, hemen bakiyorum.",
    # English technical terms inside Turkish
    "Python betiğini çalıştırdım efendim.",
    "TuneShop klasöründe bir solution dosyası ve iki proje var.",
    "GPU sıcaklığı altmış üç derece.",
    # short
    "Evet efendim.",
    "Tamam.",
]


@pytest.mark.parametrize("text", ENGLISH)
def test_english_text_is_read_by_the_english_voice(text):
    assert guess_language(text, fallback="tr") == "en"


@pytest.mark.parametrize("text", TURKISH)
def test_turkish_text_is_read_by_the_turkish_voice(text):
    assert guess_language(text, fallback="en") == "tr"


@pytest.mark.parametrize("text", ["", "123", "OK", "C:/Users/Asus"])
def test_no_evidence_falls_back(text):
    # Nothing to go on: keep the language the user spoke in.
    assert guess_language(text, fallback="tr") == "tr"
    assert guess_language(text, fallback="en") == "en"
