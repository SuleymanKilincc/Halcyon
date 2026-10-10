"""
Tests for runtime profile selection (core/profiles.py).

Profile selection decides which models load, so getting it wrong either wastes
the GPU or overflows it. The hardware is passed in as a plain object, which is
the whole trick: no GPU is needed to test what happens when there is one.
"""

import pytest

from core.hardware import Hardware
from core.profiles import BATTERY, PERFORMANCE, apply_to_voice_settings, resolve
from voice.settings import VoiceSettings


@pytest.fixture(autouse=True)
def no_profile_override(monkeypatch):
    # resolve() honours the JARVIS_PROFILE environment variable. If it happens
    # to be set on the machine running the tests, every test below would be
    # testing the override instead of the detection logic.
    monkeypatch.delenv("JARVIS_PROFILE", raising=False)


def gpu(total_gb: float, free_gb: float | None = None) -> Hardware:
    return Hardware(cuda=True, gpu_name="Test GPU", vram_gb=total_gb,
                    vram_free_gb=free_gb, cpu_physical=8)


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


def test_dev_card_gets_the_measured_configuration():
    profile = resolve(gpu(8.0, free_gb=7.07))
    assert profile.name == "gpu-9b-8k"
    assert profile.llm_model == "qwen3.5:9b"
    assert profile.llm_num_ctx == 8192
    assert profile.stt_model == "large-v3-turbo"
    assert profile.expected_first_audio_ms == 1400  # measured end to end


def test_unknown_free_memory_is_estimated_from_the_total():
    profile = resolve(gpu(8.0, free_gb=None))
    assert profile.name == "gpu-9b-8k"
    assert "estimated" in profile.reason


def test_unmeasured_configuration_does_not_invent_a_latency():
    profile = resolve(gpu(12.0, free_gb=11.2))
    assert profile.name == "gpu-9b-32k"
    assert profile.expected_first_audio_ms == 0
    assert "not measured" in profile.describe()


def test_large_card_suggests_pulling_a_bigger_model():
    profile = resolve(gpu(24.0, free_gb=23.2), installed={"qwen3.5:9b"})
    assert profile.llm_model == "qwen3.5:9b"
    assert "ollama pull qwen3.5:27b" in profile.reason


def test_nothing_suitable_installed_falls_back_to_cpu_and_says_what_to_pull():
    profile = resolve(gpu(8.0, free_gb=7.07), installed={"llama3:8b"})
    assert profile.name == BATTERY.name
    assert "ollama pull qwen3.5:9b" in profile.reason


def test_tiny_gpu_falls_back_to_cpu():
    profile = resolve(gpu(2.0, free_gb=1.5))
    assert profile.name == BATTERY.name
    assert "too little" in profile.reason


def test_performance_context_fits_entirely_in_8_gb():
    # Measured: at 16384 the 9B model spilled 16% onto the CPU; at 8192 it is
    # 100% on the GPU. If someone "helpfully" raises this, this test says why not.
    assert PERFORMANCE.llm_num_ctx == 8192


def test_explicit_override_wins_over_detection():
    profile = resolve(gpu(8.0, 7.07), override="battery")
    assert profile.name == BATTERY.name
    assert "manually" in profile.reason


def test_a_specific_gpu_plan_can_be_forced():
    assert resolve(gpu(8.0, 7.07), override="gpu-4b-8k").llm_model == "qwen3.5:4b"


def test_auto_override_means_detect():
    assert resolve(gpu(8.0, 7.07), override="auto").name == "gpu-9b-8k"


def test_environment_variable_override(monkeypatch):
    monkeypatch.setenv("JARVIS_PROFILE", "battery")
    assert resolve(gpu(8.0, 7.07)).name == BATTERY.name


def test_unknown_profile_name_is_rejected():
    with pytest.raises(ValueError):
        resolve(gpu(8.0, 7.07), override="turbo-max")


def test_apply_to_voice_settings_copies_the_speech_choices(tmp_path):
    settings = VoiceSettings(models_dir=tmp_path)
    hw = Hardware(cuda=True, vram_gb=8.0, cpu_physical=6)
    apply_to_voice_settings(PERFORMANCE, settings, hw)
    assert settings.stt.model == "large-v3-turbo"
    assert settings.stt.device == "cuda"
    assert settings.stt.compute_type_cuda == "int8_float16"
    assert settings.stt.cpu_threads == 6
