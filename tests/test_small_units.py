"""
Tests for small pure functions: Piper model paths, speech-to-text model
choice, and turn timing arithmetic.
"""

import pytest

from voice.models import VoiceModelError, piper_remote_paths
from voice.pipeline import TurnTimings
from voice.stt import Transcript, resolve_device, resolve_model


# ------------------------------------------------------------ piper paths

@pytest.mark.parametrize("voice_id, expected_onnx", [
    ("tr_TR-dfki-medium", "tr/tr_TR/dfki/medium/tr_TR-dfki-medium.onnx"),
    ("en_US-ryan-medium", "en/en_US/ryan/medium/en_US-ryan-medium.onnx"),
    # Speaker names use underscores, never hyphens, so the split stays unambiguous.
    ("en_US-hfc_female-medium", "en/en_US/hfc_female/medium/en_US-hfc_female-medium.onnx"),
])
def test_piper_voice_id_maps_to_repository_path(voice_id, expected_onnx):
    onnx, config = piper_remote_paths(voice_id)
    assert onnx == expected_onnx
    assert config == expected_onnx + ".json"


def test_malformed_voice_id_is_rejected():
    with pytest.raises(VoiceModelError):
        piper_remote_paths("tr_TR-dfki")


# ------------------------------------------------------------ stt model choice

@pytest.fixture(autouse=True)
def no_stt_override(monkeypatch):
    monkeypatch.delenv("HALCYON_STT_MODEL", raising=False)


def test_explicit_device_is_used_as_is():
    assert resolve_device("cpu") == "cpu"
    assert resolve_device("cuda") == "cuda"


def test_large_model_falls_back_to_base_on_cpu():
    # large-v3-turbo took ~13 s per sentence on this CPU; base takes ~0.5 s.
    assert resolve_model("large-v3-turbo", "cpu") == "base"


def test_large_model_is_kept_on_gpu():
    assert resolve_model("large-v3-turbo", "cuda") == "large-v3-turbo"


def test_small_model_is_kept_on_cpu():
    assert resolve_model("small", "cpu") == "small"


def test_user_choice_overrides_the_fallback(monkeypatch):
    monkeypatch.setenv("HALCYON_STT_MODEL", "large-v3-turbo")
    assert resolve_model("large-v3-turbo", "cpu") == "large-v3-turbo"


def test_transcript_with_only_whitespace_is_empty():
    assert Transcript("   ", "tr", 0.0, 500, 0).is_empty
    assert not Transcript("merhaba", "tr", 0.9, 500, 120).is_empty


# ------------------------------------------------------------ turn timings

def test_turn_timings_split_the_latency_into_stages():
    t = TurnTimings(speech_end=10.0, transcribed=10.3, first_token=10.42, first_audio=10.6)
    assert t.stt_ms == 300
    assert t.llm_first_token_ms == 120
    assert t.tts_ms == 180
    assert t.total_to_first_audio_ms == 600


def test_missing_stage_is_reported_as_minus_one_not_as_a_huge_number():
    # If the model never produced a token, first_token stays 0. Subtracting
    # from 0 would report a negative or nonsensical latency instead.
    t = TurnTimings(speech_end=10.0, transcribed=10.3)
    assert t.llm_first_token_ms == -1
    assert t.total_to_first_audio_ms == -1
