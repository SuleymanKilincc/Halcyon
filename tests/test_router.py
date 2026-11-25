"""
Tests for the conversation around mode switching (core/router.py).

The language model is a fake that records what it was asked and which model it is
"running", so the tests can check the things that matter to the user: that a big
request is answered with a question rather than a silent wait, that the wait is
named, that a yes switches and then answers the request that was waiting, that a no
is remembered, that a failed switch leaves a working assistant, and that nothing
here ever happens for an ordinary request.

The real handler yields raw text deltas; the fakes do too.
"""

import pytest

from core.modes import default_modes
from core.profiles import PERFORMANCE
from core.router import ModeController
from voice.stt import Transcript

BIG = "Bana sıfırdan bir todo uygulaması yaz"       # code, tier 2
BIG_EN = "Build a complete web app from scratch"
SMALL = "What does idempotent mean in programming?"  # code, tier 0
CHAT = "How are you today?"
DEEP = "gemma4:26b-a4b"


class FakeLLM:
    """Stands in for core.llm.SpeechLLM: records what it is told, answers with a fixed line."""

    def __init__(self, fail_warmup_for=()):
        self.profile = PERFORMANCE
        self.model = PERFORMANCE.llm_model
        self.base_system = "BASE"
        self.system = "BASE"
        self.last_tool_calls = []
        self.events = []            # "unload", "warmup:<model>", "apply:<model>", "begin", "end"
        self.asked = []             # (model, system, prompt)
        self.use_tools = True
        self.supports_thinking = True
        self.fail_warmup_for = set(fail_warmup_for)

    def tool_objects(self):
        return []

    def stream(self, prompt, system=None, language=None):
        self.asked.append((self.model, self.system, prompt))
        yield f"[{self.model}] answer"

    def unload(self):
        self.events.append("unload")

    def warmup(self):
        self.events.append(f"warmup:{self.model}")
        if self.model in self.fail_warmup_for:
            raise RuntimeError("model would not load")

    def apply_mode(self, profile, *, system=None, use_tools=True, supports_thinking=True):
        self.profile = profile
        self.model = profile.llm_model
        self.system = self.base_system if system is None else system
        self.use_tools = use_tools
        self.supports_thinking = supports_thinking
        self.events.append(f"apply:{self.model}")

    def begin_switch(self):
        self.events.append("begin")

    def end_switch(self):
        self.events.append("end")


def make(llm=None, *, installed=(DEEP,), capabilities=None, spoken=False, clock=None):
    llm = llm or FakeLLM()
    logged = []
    ticks = iter(range(0, 10_000, 24))   # each clock read is 24 "seconds" later
    controller = ModeController(
        llm,
        spoken=spoken,
        modes=default_modes({}),
        installed=lambda: None if installed is None else set(installed),
        capabilities=capabilities or (lambda model: {"completion", "tools", "thinking"}),
        log=logged.append,
        clock=clock or (lambda: next(ticks)),
    )
    return controller, llm, logged


def turn(controller, text):
    transcript = Transcript(text=text, language="tr" if any(c in text for c in "çğıöşü") else "en",
                            language_probability=1.0, duration_ms=0, latency_ms=0)
    return "".join(controller.handler(transcript))


# ------------------------------------------------------------------ ordinary requests

def test_an_ordinary_request_is_just_answered():
    controller, llm, _ = make()
    assert turn(controller, CHAT) == f"[{llm.model}] answer"
    assert llm.events == []
    assert controller.current.key == "general"


def test_a_small_code_question_never_offers_a_switch():
    controller, llm, _ = make()
    for _ in range(5):
        reply = turn(controller, SMALL)
        assert "switch" not in reply.lower() and "geç" not in reply
    assert llm.events == []


# ------------------------------------------------------------------------ the offer

def test_a_big_request_is_answered_with_a_question_not_with_an_answer():
    controller, llm, _ = make()
    reply = turn(controller, BIG_EN)
    assert reply.endswith("Shall we switch?")
    assert "30 to 120 seconds" in reply and "because" in reply
    assert llm.asked == []           # the model was not asked, nothing was loaded
    assert llm.events == []
    assert controller.pending is not None


def test_the_offer_is_in_the_language_of_the_request():
    controller, _, _ = make()
    reply = turn(controller, BIG)
    assert "Geçelim mi?" in reply and "saniye" in reply and "çünkü" in reply


def test_a_yes_switches_then_answers_the_request_that_was_waiting():
    controller, llm, _ = make()
    turn(controller, BIG_EN)
    reply = turn(controller, "yes please")

    assert "Switching to deep mode" in reply and "Deep mode is ready." in reply
    assert reply.endswith(f"[{DEEP}] answer")
    assert llm.asked == [(DEEP, llm.system, BIG_EN)]
    assert controller.current.key == "deep"
    assert controller.pending is None


def test_the_announcement_comes_before_the_load_so_it_can_be_spoken_during_it():
    controller, llm, _ = make()
    turn(controller, BIG_EN)
    transcript = Transcript(text="evet", language="tr", language_probability=1.0, duration_ms=0, latency_ms=0)
    stream = controller.handler(transcript)

    first = next(stream)
    assert "geçiyorum" in first
    assert llm.events == []          # nothing has loaded yet: the sentence goes out first
    list(stream)
    assert llm.events[0] == "begin"


def test_the_old_model_is_unloaded_before_the_new_one_loads():
    controller, llm, _ = make()
    turn(controller, BIG_EN)
    turn(controller, "yes")
    assert llm.events == ["begin", "unload", f"apply:{DEEP}", f"warmup:{DEEP}", "end"]


def test_the_history_and_the_persona_follow_the_mode():
    controller, llm, _ = make(spoken=False)
    turn(controller, BIG_EN)
    turn(controller, "yes")
    assert "deep mode" in llm.system and "fenced blocks" in llm.system     # typed persona
    assert llm.profile.llm_num_predict == 1500


def test_spoken_code_mode_does_not_ask_for_code_blocks():
    controller, llm, _ = make(spoken=True)
    turn(controller, BIG_EN)
    turn(controller, "yes")
    assert "never use code blocks" in llm.system
    assert llm.profile.llm_num_predict == 400


def test_the_measured_load_time_replaces_the_estimate_next_time():
    controller, _, _ = make()
    turn(controller, BIG_EN)
    turn(controller, "yes")                      # the fake clock makes this one 24 s
    turn(controller, "genel moda dön")
    assert "about 24 seconds" in turn(controller, BIG_EN)
    assert controller._load_seconds[DEEP] == 24


# --------------------------------------------------------------------------- a no

def test_a_no_answers_the_request_where_we_are():
    controller, llm, _ = make()
    turn(controller, BIG_EN)
    reply = turn(controller, "no thanks")
    assert reply.startswith("All right, staying in general mode.")
    assert reply.endswith(f"[{PERFORMANCE.llm_model}] answer")
    assert llm.events == []


def test_a_no_is_remembered_so_the_assistant_does_not_nag():
    controller, llm, _ = make()
    turn(controller, BIG_EN)
    turn(controller, "no")
    for _ in range(controller.COOLDOWN_TURNS - 1):
        reply = turn(controller, BIG_EN)
        assert "Shall we" not in reply
    assert llm.events == []


def test_after_the_cooldown_it_may_ask_again():
    controller, _, _ = make()
    turn(controller, BIG_EN)
    turn(controller, "no")
    for _ in range(controller.COOLDOWN_TURNS):
        turn(controller, CHAT)
    assert "Shall we switch?" in turn(controller, BIG_EN)


def test_something_else_lets_the_question_lapse_and_is_answered_as_a_new_request():
    controller, llm, _ = make()
    turn(controller, BIG_EN)
    reply = turn(controller, CHAT)
    assert reply == f"[{PERFORMANCE.llm_model}] answer"
    assert controller.pending is None
    assert llm.events == []


# ----------------------------------------------------------------- a coding session

def test_three_pieces_of_code_work_in_a_row_become_a_session():
    controller, _, _ = make()
    assert "Shall we" not in turn(controller, "Write a function that reverses a string")
    assert "Shall we" not in turn(controller, "Now write a function that sorts a list")
    assert "Shall we switch?" in turn(controller, "And write a function that merges two lists")


def test_a_question_in_between_breaks_the_streak():
    controller, _, _ = make()
    turn(controller, "Write a function that reverses a string")
    turn(controller, "Now write a function that sorts a list")
    turn(controller, CHAT)
    assert "Shall we" not in turn(controller, "And write a function that merges two lists")


# ------------------------------------------------------------------- named, missing

def test_a_named_mode_switches_without_asking():
    controller, llm, _ = make()
    reply = turn(controller, "kod moduna geç")
    assert "Derin moda geçiyorum" in reply and "Derin mod hazır." in reply
    assert controller.current.key == "deep"
    assert "unload" in llm.events


def test_asking_for_the_mode_we_are_in_says_so():
    controller, _, _ = make()
    turn(controller, "switch to code mode")
    assert turn(controller, "switch to code mode") == "We are already in deep mode."


def test_a_missing_model_is_said_once_and_the_request_is_still_answered():
    controller, llm, logged = make(installed=())
    first = turn(controller, BIG_EN)
    assert first.startswith("Deep mode needs a model that is not installed yet")
    assert first.endswith("answer")
    assert any("ollama pull gemma4:26b-a4b" in line for line in logged)

    second = turn(controller, BIG_EN)
    assert "not installed" not in second          # said once, not on every turn
    assert llm.events == []


def test_an_unreachable_ollama_is_not_taken_for_a_missing_model():
    controller, llm, _ = make(installed=None)
    assert "Shall we switch?" in turn(controller, BIG_EN)


# ------------------------------------------------------------------------- failure

def test_a_failed_switch_leaves_a_working_assistant():
    llm = FakeLLM(fail_warmup_for={DEEP})
    controller, llm, logged = make(llm)
    turn(controller, BIG_EN)
    reply = turn(controller, "yes")

    assert "The switch did not work, so I am staying in general mode." in reply
    assert controller.current.key == "general"
    assert llm.model == PERFORMANCE.llm_model                  # rolled back
    assert reply.endswith(f"[{PERFORMANCE.llm_model}] answer") # and the request was still answered
    assert any("failed" in line for line in logged)
    assert llm.events[-1] == "end"           # the swap flag is always released


# ---------------------------------------------------------------- capabilities, tools

def test_a_model_without_tools_or_thinking_is_told_neither():
    controller, llm, _ = make(capabilities=lambda model: {"completion"})
    turn(controller, BIG_EN)
    turn(controller, "yes")
    assert llm.use_tools is False and llm.supports_thinking is False


def test_unknown_capabilities_keep_the_defaults():
    controller, llm, _ = make(capabilities=lambda model: None)
    turn(controller, BIG_EN)
    turn(controller, "yes")
    assert llm.use_tools is True and llm.supports_thinking is True


# ------------------------------------------------------------------- going back

def test_after_the_conversation_moves_on_it_offers_to_go_back():
    controller, _, _ = make()
    turn(controller, "kod moduna geç")
    for _ in range(controller.OFF_TOPIC_TURNS - 1):
        assert "dönelim mi" not in turn(controller, CHAT)
    reply = turn(controller, CHAT)
    assert "Shall we go back to general mode?" in reply
    assert "because the models swap places" in reply


def test_yes_to_going_back_returns_to_the_general_model_and_answers():
    controller, llm, _ = make()
    turn(controller, "kod moduna geç")
    for _ in range(controller.OFF_TOPIC_TURNS):
        turn(controller, CHAT)
    reply = turn(controller, "yes")
    assert controller.current.key == "general"
    assert llm.model == PERFORMANCE.llm_model
    assert llm.system == "BASE"
    assert reply.endswith(f"[{PERFORMANCE.llm_model}] answer")


def test_code_questions_in_code_mode_never_offer_to_leave():
    controller, _, _ = make()
    turn(controller, "kod moduna geç")
    for _ in range(6):
        assert "Shall we" not in turn(controller, SMALL)


# ---------------------------------------------------------------- the soft mode

def test_a_mode_that_only_changes_the_prompt_loads_nothing_and_asks_nothing():
    controller, llm, _ = make()
    reply = turn(controller, "Research the pros and cons of electric cars in depth, with detailed reports and sources")
    assert "Switching to research mode." in reply and "Research mode is ready." in reply
    assert "unload" not in llm.events and not any(e.startswith("warmup") for e in llm.events)
    assert "Research mode" in llm.system and llm.system.startswith("BASE")
    assert reply.endswith("answer")


def test_status_says_the_mode_and_how_the_request_was_read():
    controller, _, _ = make()
    turn(controller, BIG_EN)
    assert controller.status() == "mode: general | request: code tier 2 | waiting for your answer"


def test_a_mode_profile_is_derived_so_the_gpu_planner_ladder_is_untouched():
    controller, llm, _ = make()
    turn(controller, "switch to code mode")
    assert llm.profile.name == f"{PERFORMANCE.name}+deep"
    assert llm.profile.llm_model == DEEP


@pytest.mark.parametrize("text", [BIG, BIG_EN])
def test_the_big_request_waits_in_either_language(text):
    controller, _, _ = make()
    turn(controller, text)
    assert controller.pending.prompt == text


# --------------------------------------------------------------- deep mode and the packs

def test_a_story_request_offers_deep_mode_and_says_it_is_a_story():
    controller, llm, _ = make()
    reply = turn(controller, "Let us role-play: you are the game master of a fantasy world")
    assert "a longer story to build" in reply and reply.endswith("Shall we switch?")
    assert llm.events == []
    assert turn(controller, "yes").endswith(f"[{DEEP}] answer")
    assert controller.current.key == "deep"


def test_one_deep_mode_serves_code_and_stories_so_a_story_in_deep_mode_asks_nothing():
    controller, llm, _ = make()
    turn(controller, "switch to deep mode")
    llm.events.clear()
    for _ in range(4):
        reply = turn(controller, "Write a long story with many characters set in a world without metal")
        assert "Shall we" not in reply
    assert llm.events == []


def test_a_machine_too_small_for_any_pack_has_no_deep_mode_and_is_never_offered_one():
    from core.hardware import Hardware

    llm = FakeLLM()
    controller = ModeController(llm, spoken=False, modes=default_modes({}, Hardware(cuda=True, vram_gb=4, ram_gb=8)),
                                installed=lambda: None, log=lambda line: None)
    assert "deep" not in controller.modes
    assert "Shall we" not in turn(controller, BIG_EN)
    assert llm.events == []


def test_the_missing_model_message_names_the_pack_and_its_size():
    controller, _, logged = make(installed=())
    turn(controller, BIG_EN)
    assert any("Standard pack, about 18 GB" in line and "ollama pull gemma4:26b-a4b" in line for line in logged)


# ------------------------------------------------------- found in review

def test_refusing_a_mode_by_name_never_switches_to_it():
    controller, llm, _ = make()
    reply = turn(controller, "I don't want to switch to deep mode")
    assert controller.current.key == "general" and llm.events == []
    assert reply == f"[{PERFORMANCE.llm_model}] answer"
    assert "Shall we" not in turn(controller, BIG_EN)        # and it is not offered right after


def test_a_refusal_in_a_sentence_answers_the_waiting_request_here():
    controller, llm, _ = make()
    turn(controller, BIG_EN)
    reply = turn(controller, "No, just do it here")
    assert reply.startswith("All right, staying in general mode.")
    assert llm.asked[-1][2] == BIG_EN                         # the request that was waiting
    assert llm.events == []


def test_a_refusal_with_a_new_request_attached_answers_the_new_request():
    controller, llm, _ = make()
    turn(controller, BIG_EN)
    turn(controller, "No, instead tell me what the capital of France is please")
    assert llm.asked[-1][2].startswith("No, instead")
    assert llm.events == []


def test_research_mode_from_deep_mode_quotes_a_real_wait_not_zero():
    controller, _, _ = make()
    turn(controller, "switch to deep mode")
    reply = turn(controller, "Research the pros and cons of electric cars in depth, with detailed reports and sources")
    assert "0 to 0" not in reply and "15 to 30 seconds" in reply


def test_entering_a_mode_by_name_does_not_offer_to_leave_it_on_the_next_turn():
    controller, _, _ = make()
    for _ in range(3):
        turn(controller, CHAT)
    turn(controller, "switch to deep mode")
    assert "Shall we go back" not in turn(controller, CHAT)


def test_after_a_startup_step_down_general_mode_is_the_smaller_model():
    """fit_to_gpu may step down after the controller exists; leaving a mode must not reload the bigger model."""
    from dataclasses import replace

    controller, llm, _ = make()
    smaller = replace(PERFORMANCE, llm_model="qwen3.5:4b")
    llm.apply_mode(smaller)                  # what fit_to_gpu does through the client
    controller.rebase()
    turn(controller, "switch to deep mode")
    turn(controller, "genel moda dön")
    assert llm.model == "qwen3.5:4b"
