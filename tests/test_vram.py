"""
Tests for the VRAM planner (core/vram.py).

No GPU is needed to test what the planner would choose for one: the free
memory is just a number. The calibration tests pin the planner to outcomes
that were actually observed on real hardware.
"""

import pytest

from core.vram import (
    HEADROOM_GIB,
    LADDER,
    LLM_GIB,
    PLANS_BY_NAME,
    WHISPER_GIB,
    Plan,
    choose,
    fits,
    step_down,
)

# Free VRAM measured on the development machine (RTX 4060 Laptop, 8 GB) with
# nothing loaded. It varied between runs with what else was open.
FREE_ON_DEV_CARD = (7.07, 7.16)


# ------------------------------------------------------------ calibration

@pytest.mark.parametrize("free", FREE_ON_DEV_CARD)
def test_chooses_the_configuration_measured_to_fit_the_dev_card(free):
    # 9B at 8k with the large Whisper ran 100% on the GPU.
    plan, _ = choose(free)
    assert plan == Plan("qwen3.5:9b", 8192, "large-v3-turbo")


@pytest.mark.parametrize("free", FREE_ON_DEV_CARD)
def test_rejects_the_configuration_measured_to_spill_on_the_dev_card(free):
    # 9B at 16k spilled onto the CPU even with nothing else loaded.
    assert not fits(Plan("qwen3.5:9b", 16384, "large-v3-turbo"), free)


# ------------------------------------------------------------ other cards
# Typical free VRAM: total minus what the desktop and other programs hold.

@pytest.mark.parametrize("card, free, expected", [
    ("RTX 3050 4 GB", 3.3, "gpu-2b-8k-small"),
    ("RTX 3060 Laptop 6 GB", 5.2, "gpu-4b-8k"),
    ("RTX 4060 Laptop 8 GB", 7.07, "gpu-9b-8k"),
    ("RTX 3060 12 GB", 11.2, "gpu-9b-32k"),
    ("RTX 4080 16 GB", 15.2, "gpu-9b-32k"),
    ("RTX 4090 24 GB", 23.2, "gpu-27b-32k"),
    ("RTX 5090 32 GB", 31.2, "gpu-27b-32k"),
])
def test_each_card_gets_the_best_configuration_that_fits(card, free, expected):
    plan, _ = choose(free)
    assert plan is not None, card
    assert plan.name == expected, card
    assert plan.needed_gib + HEADROOM_GIB <= free, card


def test_a_card_too_small_for_anything_gets_no_gpu_plan():
    plan, best = choose(2.0)
    assert plan is None and best is None


def test_more_memory_never_gives_a_worse_plan():
    # Walk free memory upwards; the chosen rung may only move up the ladder.
    previous = len(LADDER)
    for tenths in range(20, 340):
        plan, _ = choose(tenths / 10)
        rank = LADDER.index(plan) if plan else len(LADDER)
        assert rank <= previous, f"{tenths / 10} GiB chose a worse plan than less memory did"
        previous = rank


# ------------------------------------------------------------ installed models

def test_only_installed_models_are_chosen_and_a_better_one_is_suggested():
    plan, best = choose(23.2, installed={"qwen3.5:9b", "qwen3.5:2b"})
    assert plan.llm_model == "qwen3.5:9b"
    assert best.llm_model == "qwen3.5:27b"


def test_when_nothing_suitable_is_installed_no_plan_is_chosen():
    plan, best = choose(7.07, installed={"some-other-model:7b"})
    assert plan is None
    assert best is not None  # the card could run something if it were pulled


# ------------------------------------------------------------ stepping down

def test_step_down_moves_to_the_next_rung():
    assert step_down(PLANS_BY_NAME["gpu-9b-16k"]) == PLANS_BY_NAME["gpu-9b-8k"]


def test_step_down_can_change_the_speech_model_too():
    # Whisper is loaded after the language model is checked, so a spilled
    # 4B + large Whisper may fall back to 4B + small Whisper.
    assert step_down(PLANS_BY_NAME["gpu-4b-8k"]) == PLANS_BY_NAME["gpu-4b-8k-small"]


def test_step_down_skips_models_that_are_not_installed():
    lower = step_down(PLANS_BY_NAME["gpu-9b-8k"], installed={"qwen3.5:2b"})
    assert lower.llm_model == "qwen3.5:2b"


def test_bottom_rung_has_nothing_below():
    assert step_down(LADDER[-1]) is None


# ------------------------------------------------------------ table integrity

def test_plan_names_are_unique():
    # Two plans once shared the name "gpu-4b-8k"; lookups by name would have
    # silently returned the wrong one.
    names = [p.name for p in LADDER]
    assert len(names) == len(set(names))


def test_every_rung_has_measurements_for_its_models():
    for plan in LADDER:
        assert plan.num_ctx in LLM_GIB[plan.llm_model]
        assert plan.stt_model in WHISPER_GIB


def test_ladder_is_ordered_from_most_to_least_memory_within_each_model():
    for model in {p.llm_model for p in LADDER}:
        sizes = [p.needed_gib for p in LADDER if p.llm_model == model]
        assert sizes == sorted(sizes, reverse=True), model


def test_unmeasured_model_is_flagged_as_an_estimate():
    assert Plan("qwen3.5:27b", 8192, "large-v3-turbo").estimated
    assert not Plan("qwen3.5:9b", 8192, "large-v3-turbo").estimated


# ------------------------------------------------ memory held by an idle Ollama model

def test_memory_held_by_loaded_models_is_summed():
    from core.vram import resident_vram_gib

    payload = {"models": [{"name": "a", "size_vram": 5 * 2**30}, {"name": "b", "size_vram": 2**30}]}
    assert resident_vram_gib(payload) == 6.0


def test_no_loaded_models_hold_nothing():
    from core.vram import resident_vram_gib

    assert resident_vram_gib({}) == 0.0
    assert resident_vram_gib({"models": []}) == 0.0


def test_an_unreachable_ollama_counts_as_zero():
    from core.vram import ollama_resident_gib

    # Port 9 (discard) refuses connections; a normal "Ollama is not running" case.
    assert ollama_resident_gib("http://127.0.0.1:9", timeout=0.5) == 0.0


# ------------------------------------------------- the window: typing first

from core.vram import TYPING_LADDER, speech_model_now  # noqa: E402

QWEN = {"qwen3.5:9b", "qwen3.5:4b", "qwen3.5:2b"}


def test_with_the_memory_the_window_found_typing_gets_the_9b_model_and_the_small_whisper():
    """Measured: 6.7 GB free with the desktop open. 9B + large Whisper missed by 0.05 GB."""
    assert choose(6.7, QWEN)[0].name == "gpu-4b-8k"                            # speaking first
    assert choose(6.7, QWEN, TYPING_LADDER)[0].name == "gpu-9b-8k-small"       # typing first


def test_typing_still_takes_the_large_whisper_when_it_fits():
    """7.1 GB was the usual free memory: the window kept the large Whisper, and still does."""
    assert choose(7.1, QWEN, TYPING_LADDER)[0].name == "gpu-9b-8k"


def test_typing_never_trades_the_large_whisper_for_a_longer_context():
    for free in [x / 10 for x in range(30, 200)]:
        plan = choose(free, QWEN, TYPING_LADDER)[0]
        voice = choose(free, QWEN)[0]
        if plan and voice and plan.llm_model == voice.llm_model:
            assert plan == voice, free


def test_the_typing_ladder_keeps_every_voice_rung_in_order():
    names = [p.name for p in TYPING_LADDER]
    assert [n for n in names if n in {p.name for p in LADDER}] == [p.name for p in LADDER]
    assert len(names) == len(set(names))
    assert all(p.name in PLANS_BY_NAME for p in TYPING_LADDER)


def test_a_typing_plan_that_spills_steps_to_the_small_whisper_before_a_smaller_model():
    assert step_down(PLANS_BY_NAME["gpu-9b-16k"], QWEN, TYPING_LADDER).name == "gpu-9b-8k"
    assert step_down(PLANS_BY_NAME["gpu-9b-8k"], QWEN, TYPING_LADDER).name == "gpu-9b-8k-small"
    assert step_down(PLANS_BY_NAME["gpu-9b-8k-small"], QWEN).name == "gpu-4b-8k"
    assert step_down(PLANS_BY_NAME["gpu-9b-16k"], QWEN).name == "gpu-9b-8k"        # voice: unchanged


@pytest.mark.parametrize("free, expected", [
    (WHISPER_GIB["large-v3-turbo"] + HEADROOM_GIB, "large-v3-turbo"),
    (WHISPER_GIB["large-v3-turbo"] + HEADROOM_GIB - 0.01, "small"),
    (None, "small"),
])
def test_the_microphone_gets_the_large_whisper_only_when_it_fits_beside_the_loaded_model(free, expected):
    assert speech_model_now("small", free) == expected


def test_a_plan_with_the_large_whisper_keeps_it():
    assert speech_model_now("large-v3-turbo", 0.1) == "large-v3-turbo"
