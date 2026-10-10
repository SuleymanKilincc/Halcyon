"""
Tests for runtime profile selection (core/profiles.py).

Profile selection decides which models load, so getting it wrong either wastes
the GPU or overflows it. The hardware is passed in as a plain object, which is
the whole trick: no GPU is needed to test what happens when there is one.
"""

import pytest

from core.hardware import Hardware
from core.profiles import (
    BATTERY,
    MIN_VRAM_FOR_9B_GB,
    PERFORMANCE,
    PERFORMANCE_LOW_VRAM,
    apply_to_voice_settings,
    resolve,
)
from voice.settings import VoiceSettings


@pytest.fixture(autouse=True)
def no_profile_override(monkeypatch):
    # resolve() honours the JARVIS_PROFILE environment variable. If it happens
    # to be set on the machine running the tests, every test below would be
    # testing the override instead of the detection logic.
    monkeypatch.delenv("JARVIS_PROFILE", raising=False)


def gpu(vram_gb: float) -> Hardware:
    return Hardware(cuda=True, gpu_name="Test GPU", vram_gb=vram_gb, cpu_physical=8)


def test_no_cuda_selects_battery():
    profile = resolve(Hardware(cuda=False))
    assert profile.name == BATTERY.name
    assert profile.llm_model == "qwen3.5:2b"
    assert profile.stt_device == "cpu"


def test_switched_off_gpu_is_explained_not_silently_ignored():
    hw = Hardware(cuda=False, dgpu_disconnected=True, dgpu_name="RTX Test")
    profile = resolve(hw)
    assert profile.name == BATTERY.name
    assert "RTX Test" in profile.reason
    assert "Code 45" in profile.reason


def test_gpu_with_enough_vram_selects_performance():
    profile = resolve(gpu(8.0))
    assert profile.name == PERFORMANCE.name
    assert profile.llm_model == "qwen3.5:9b"
    assert profile.stt_device == "cuda"


def test_performance_context_fits_entirely_in_8_gb():
    # Measured: at 16384 the 9B model spilled 16% onto the CPU; at 8192 it is
    # 100% on the GPU. If someone "helpfully" raises this, this test says why not.
    assert PERFORMANCE.llm_num_ctx == 8192


def test_small_gpu_selects_low_vram_profile():
    profile = resolve(gpu(6.0))
    assert profile.name == PERFORMANCE_LOW_VRAM.name
    assert profile.llm_model == "qwen3.5:4b"
    assert profile.stt_device == "cuda"  # keeps the fast speech recognition


def test_vram_exactly_at_the_threshold_counts_as_enough():
    # Boundary values are where off-by-one bugs live: is the limit inclusive?
    assert resolve(gpu(MIN_VRAM_FOR_9B_GB)).name == PERFORMANCE.name
    assert resolve(gpu(MIN_VRAM_FOR_9B_GB - 0.01)).name == PERFORMANCE_LOW_VRAM.name


def test_explicit_override_wins_over_detection():
    profile = resolve(gpu(8.0), override="battery")
    assert profile.name == BATTERY.name
    assert "manually" in profile.reason


def test_environment_variable_override(monkeypatch):
    monkeypatch.setenv("JARVIS_PROFILE", "battery")
    assert resolve(gpu(8.0)).name == BATTERY.name


def test_unknown_profile_name_is_rejected():
    with pytest.raises(ValueError):
        resolve(gpu(8.0), override="turbo-max")


def test_apply_to_voice_settings_copies_the_speech_choices(tmp_path):
    settings = VoiceSettings(models_dir=tmp_path)
    hw = Hardware(cuda=True, vram_gb=8.0, cpu_physical=6)
    apply_to_voice_settings(PERFORMANCE, settings, hw)
    assert settings.stt.model == "large-v3-turbo"
    assert settings.stt.device == "cuda"
    assert settings.stt.compute_type_cuda == "int8_float16"
    assert settings.stt.cpu_threads == 6
