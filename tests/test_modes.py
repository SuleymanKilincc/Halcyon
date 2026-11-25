"""
Tests for the mode rules (core/modes.py): how a request is placed, how the user's
answers are read, and what the assistant says.

Nothing here needs a model. The classifier is rule-based on purpose, so every rule
is pinned by an example: when a request is misplaced in live use, the fix is a
new row here followed by a change to the rule.
"""

import pytest

from core.modes import (
    GENERAL,
    SAY,
    classify,
    deep_mode,
    default_modes,
    explicit_mode,
    is_refusal,
    parse_confirmation,
    refused_mode,
    say,
    seconds_phrase,
)
from core.packs import PACKS
from voice.tts import is_closing_offer

# --------------------------------------------------------------------------- tiers

TIER_0 = [
    "What does idempotent mean in programming?",
    "Python'da bir döngü nedir?",
    "What is a regex?",
    "Bu kod ne demek?",
]
TIER_1 = [
    "Write a function that reverses a string",
    "Bir fonksiyon yaz, listedeki çift sayıları bulsun",
    "Why does this traceback happen: KeyError: 'name'",
    "main.py dosyasındaki hatayı düzelt",
    "Explain this code:\n```python\ndef f(x):\n    return x * 2\n```",
    "Write a script that renames my files",
    "Optimize this SQL query",
]
TIER_2 = [
    "Write me a todo app from scratch",
    "Bana bir todo uygulaması yaz",
    "Build a complete website with a backend and a frontend",
    "Tüm proje için baştan sona bir mimari kur",
    "Develop an application that tracks expenses",
    "Refactor the whole codebase into modules",
    "Create a project with multiple files and tests",
]


@pytest.mark.parametrize("text", TIER_0)
def test_a_small_question_about_code_stays_tier_0(text):
    intent = classify(text)
    assert (intent.category, intent.tier) == ("code", 0), intent


@pytest.mark.parametrize("text", TIER_1)
def test_a_piece_of_code_work_is_tier_1(text):
    intent = classify(text)
    assert (intent.category, intent.tier) == ("code", 1), intent


@pytest.mark.parametrize("text", TIER_2)
def test_a_whole_job_is_tier_2(text):
    intent = classify(text)
    assert (intent.category, intent.tier) == ("code", 2), intent


def test_a_long_paste_is_tier_2():
    pasted = "\n".join(f"    x{i} = compute({i})" for i in range(70))
    assert classify("Review this:\n" + pasted).tier == 2


def test_a_short_paste_is_not():
    pasted = "def add(a, b):\n    return a + b\n"
    assert classify("What does this do?\n" + pasted).tier <= 1


# ---------------------------------------------------------------------------- stories

STORY_TIER_0 = [
    "Hikaye nedir?",
    "What makes a good story?",
]
STORY_TIER_1 = [
    "Bana kısa bir hikaye yaz",
    "Write a short story about a lighthouse keeper",
]
STORY_TIER_2 = [
    "Let us role-play: you are the game master of a fantasy world",
    "Rol yapalım, sen oyun yöneticisi ol, dünyayı ve karakterleri yönet",
    "Write a long story with many characters set in a world without metal",
    "Baştan uzun bir senaryo kur, dünyası ve karakterleri olsun",
    "Build a world for a text adventure",
]


@pytest.mark.parametrize("text", STORY_TIER_0)
def test_a_question_about_stories_stays_tier_0(text):
    intent = classify(text)
    assert (intent.category, intent.tier) == ("story", 0), intent


@pytest.mark.parametrize("text", STORY_TIER_1)
def test_a_small_piece_of_writing_is_tier_1(text):
    intent = classify(text)
    assert (intent.category, intent.tier) == ("story", 1), intent


@pytest.mark.parametrize("text", STORY_TIER_2)
def test_a_world_to_keep_track_of_is_tier_2(text):
    intent = classify(text)
    assert (intent.category, intent.tier) == ("story", 2), intent


@pytest.mark.parametrize("text", [
    "Write a test scenario for this function",
    "Bu fonksiyon için bir test senaryosu yaz: def add(a, b): return a + b",
    "Plot the data with matplotlib in python",
])
def test_scenario_and_plot_next_to_code_are_still_code(text):
    assert classify(text).category == "code"


# ------------------------------------------------------------------- other categories

@pytest.mark.parametrize("text, category, tier", [
    ("How are you today?", "chat", 0),
    ("Bugün nasılsın?", "chat", 0),
    ("What is on my desktop?", "daily", 0),
    ("Masaüstümde neler var?", "daily", 0),
    ("What is the capital of France?", "research", 0),
    ("Türkiye'nin başkenti neresi?", "research", 0),
    ("Research the pros and cons of electric cars", "research", 1),
    ("Bu konuda kapsamlı bir araştırma yap ve kaynakları karşılaştır", "research", 2),
])
def test_everything_else_is_placed_in_its_own_category(text, category, tier):
    intent = classify(text)
    assert (intent.category, intent.tier) == (category, tier), intent


def test_the_turkish_verb_git_is_not_the_version_control_tool():
    assert classify("markete git").category != "code"
    assert classify("git commit mesajını düzelt").category == "code"


def test_a_file_name_makes_it_code():
    assert classify("main.py ne yapıyor?").category == "code"


# ----------------------------------------------------------------------- answers

@pytest.mark.parametrize("text", [
    "Evet", "evet geç", "Tamam, geçelim.", "olur", "Yes", "yes please", "sure", "go ahead", "do it", "Okay!",
])
def test_a_yes_is_read_as_yes(text):
    assert parse_confirmation(text) == "yes"


@pytest.mark.parametrize("text", [
    "Hayır", "hayır teşekkürler", "gerek yok", "kalsın", "no", "No thanks", "not now", "don't",
])
def test_a_no_is_read_as_no(text):
    assert parse_confirmation(text) == "no"


@pytest.mark.parametrize("text", [
    "geç kaldım",                       # "I am late": contains "geç", is not an answer
    "Evet ve şimdi bir fonksiyon yaz",  # a yes with a new request attached is a new request
    "What time is it?",
    "It",
    "",
    "tamam ama önce şunu söyle, hava nasıl olacak yarın",
])
def test_anything_else_is_not_an_answer(text):
    assert parse_confirmation(text) is None


@pytest.mark.parametrize("text, key", [
    ("kod moduna geç", "deep"),
    ("Kodlama moduna geçelim", "deep"),
    ("derin moda geç", "deep"),
    ("senaryo moduna geçelim", "deep"),
    ("switch to code mode", "deep"),
    ("switch to deep mode", "deep"),
    ("genel moda dön", "general"),
    ("go back to general mode", "general"),
    ("araştırma moduna geç", "research"),
])
def test_a_named_mode_is_recognised(text, key):
    assert explicit_mode(text) == key


@pytest.mark.parametrize("text", [
    "kod modu nedir",
    "what is code mode",
    "bana bir fonksiyon yaz",
    "kod moduna geçmeden önce şunu açıklar mısın, bu hata neden oluyor ve nasıl çözülür",  # too long to be a command
])
def test_a_question_about_a_mode_is_not_a_command(text):
    assert explicit_mode(text) is None


# ----------------------------------------------------------------------- sentences

def test_the_deep_model_can_be_chosen_from_the_environment():
    standard = PACKS[0]
    assert deep_mode(standard, {"HALCYON_DEEP_MODEL": "some-model:7b"}).model == "some-model:7b"
    assert deep_mode(standard, {}).model == standard.deep_model
    assert deep_mode(None, {"HALCYON_DEEP_MODEL": "some-model:7b"}).model == "some-model:7b"
    assert deep_mode(None, {}) is None            # no pack fits and nothing was named: no deep mode


def test_deep_mode_serves_code_and_stories():
    deep = default_modes({})["deep"]
    assert set(deep.categories) == {"code", "story"}
    assert deep.download_note == "Standard pack, about 18 GB"


def test_the_assistant_gives_the_wait_and_the_reason_in_the_users_language():
    deep = default_modes()["deep"]
    english = say("ask_switch", "en", mode=deep, current=GENERAL, seconds=seconds_phrase("en", deep.load_seconds))
    turkish = say("ask_switch", "tr", mode=deep, current=GENERAL, seconds=seconds_phrase("tr", deep.load_seconds))
    assert "about 30 to 120 seconds" in english and "because" in english
    assert "yaklaşık 30 ile 120 saniye" in turkish and "çünkü" in turkish


def test_the_offer_says_what_kind_of_work_it_is():
    deep = default_modes()["deep"]
    code = say("ask_switch", "en", mode=deep, current=GENERAL, seconds="x", category="code")
    story = say("ask_switch", "en", mode=deep, current=GENERAL, seconds="x", category="story")
    other = say("ask_switch", "en", mode=deep, current=GENERAL, seconds="x")
    assert "a bigger coding job" in code and "a longer story to build" in story and "a heavier job" in other
    assert "kurulması gereken uzun bir senaryo" in say("ask_switch", "tr", mode=deep, current=GENERAL,
                                                         seconds="x", category="story")


def test_a_measured_switch_replaces_the_guess():
    assert seconds_phrase("en", (20, 30), measured=24.4) == "about 24"
    assert seconds_phrase("tr", (20, 30), measured=24.4) == "yaklaşık 24"


def test_turkish_case_endings_follow_the_mode():
    deep, general = default_modes()["deep"], GENERAL
    assert say("switching_soft", "tr", mode=deep) == "Derin moda geçiyorum."
    assert say("already", "tr", mode=general) == "Zaten genel moddayız."
    assert say("declined", "tr", mode=deep) == "Tamam, derin modda devam ediyorum."


def test_an_unknown_language_falls_back_to_english():
    assert say("ready", "de", mode=default_modes()["deep"]) == "Deep mode is ready."


def test_no_spoken_sentence_starts_like_a_closing_offer():
    """
    voice/tts.py drops sentences like "Shall I ..." that follow an answer. The question
    "Shall we switch?" comes after other sentences of ours, so it must not be one of them.
    """
    modes = default_modes()
    for language in SAY:
        for key in SAY[language]:
            text = say(key, language, mode=modes["deep"], current=modes["general"], seconds="x")
            for sentence in text.replace("?", "?.").split("."):
                assert not is_closing_offer(sentence), (language, key, sentence)


# ------------------------------------------------------- refusals (found in review)

@pytest.mark.parametrize("text", [
    "I don't want to switch to deep mode",
    "I don\u2019t want to switch to deep mode",          # the apostrophe a phone keyboard types
    "do not switch to code mode",
    "never use deep mode",
    "derin moda geçme",
    "kod moduna geçmeyelim",
    "derin modu istemiyorum",
    "genel moda dönme",
])
def test_a_refusal_that_names_a_mode_is_not_a_request_for_it(text):
    assert explicit_mode(text) is None
    assert refused_mode(text) is not None
    assert is_refusal(text)


@pytest.mark.parametrize("text", [
    "No, just do it here",
    "Hayır, burada devam et",
    "Nope, stay where we are",
    "I'd rather not switch",
    "No thanks, answer it here",
])
def test_a_refusal_in_a_sentence_is_read_as_no(text):
    assert is_refusal(text)


@pytest.mark.parametrize("text", [
    "yes please",
    "Write me a function that sorts a list",
    "What does deep mode do?",
    "switch to deep mode",
    "Bunu şimdi yap",
])
def test_an_answer_or_a_request_is_not_a_refusal(text):
    assert not is_refusal(text)


def test_an_inflected_turkish_coding_request_is_recognised():
    """'kod' with a long Turkish ending used to fall outside the rule and read as chat."""
    intent = classify("Kodlamalarımızı baştan sona incele")
    assert (intent.category, intent.tier) == ("code", 2), intent
