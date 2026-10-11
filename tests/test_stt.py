"""
Tests for speech-recognition post-processing (voice/stt.py).

Whisper is replaced by a fake model that returns scripted segments, so these
run without the model, a GPU or any download. What is tested is our logic
around Whisper: dropping wrong-language and phantom transcripts, and
loading from the local cache before ever touching the network.
"""

import sys
import types
from dataclasses import dataclass, field

import numpy as np
import pytest

from voice.settings import SAMPLE_RATE, STTSettings
from voice.stt import Transcriber, is_phantom

AUDIO = np.zeros(SAMPLE_RATE, dtype=np.float32)  # one second; long enough to be transcribed


@dataclass
class Segment:
    text: str


@dataclass
class Info:
    language: str
    language_probability: float
    all_language_probs: list = field(default_factory=list)


class FakeWhisper:
    """Returns a scripted result for each requested language (None = auto-detect)."""

    def __init__(self, results):
        self.results = results
        self.requested = []

    def transcribe(self, audio, language=None, **options):
        self.requested.append(language)
        text, info = self.results[language]
        return iter([Segment(text)]), info


def transcriber_with(fake, **settings) -> Transcriber:
    t = Transcriber.__new__(Transcriber)  # skip __init__: no real model is loaded
    t.settings = STTSettings(**settings)
    t._model = fake
    return t


PORTUGUESE_GUESS = {
    # Noisy Turkish that Whisper took for Portuguese - observed in bench/stt_eval.py.
    None: ("Só um vídeo que eu gostei antes.",
           Info("pt", 0.62, [("pt", 0.62), ("tr", 0.21), ("en", 0.04)])),
}


# ------------------------------------------------------------ wrong language

def test_audio_detected_as_another_language_is_dropped_as_not_understood():
    # In the benchmark, every clip detected as a third language was
    # unintelligible; acting on it would mean acting on garbage.
    fake = FakeWhisper(PORTUGUESE_GUESS)
    result = transcriber_with(fake).transcribe(AUDIO)
    assert result.text == ""
    assert result.dropped == "unintelligible"
    assert result.is_empty                    # so the pipeline never sends it to the LLM
    assert result.language == "tr"            # the most probable candidate
    assert result.detected_language == "pt"   # the wrong detection stays visible
    assert fake.requested == [None]           # decoded once; no second pass


def test_without_dropping_the_old_behaviour_only_relabels():
    # The original behaviour: Portuguese text under a Turkish label, with
    # nothing downstream able to tell.
    fake = FakeWhisper(PORTUGUESE_GUESS)
    result = transcriber_with(fake, drop_other_languages=False).transcribe(AUDIO)
    assert result.text.startswith("Só um vídeo")
    assert result.language == "tr"


def test_a_candidate_language_is_decoded_only_once():
    fake = FakeWhisper({None: ("Hello there.", Info("en", 0.97, [("en", 0.97), ("tr", 0.01)]))})
    result = transcriber_with(fake).transcribe(AUDIO)
    assert result.language == "en"
    assert fake.requested == [None]


def test_a_forced_language_skips_detection():
    fake = FakeWhisper({"tr": ("Merhaba.", Info("tr", 1.0))})
    result = transcriber_with(fake).transcribe(AUDIO, language="tr")
    assert result.text == "Merhaba."
    assert fake.requested == ["tr"]


# ------------------------------------------------------------ phantoms

@pytest.mark.parametrize("text", ["Thank you.", "you", "  YOU ", "E aí", "Продолжение следует...",
                                  "Jangan lupa like, share, dan subscribe"])
def test_known_phantom_phrases_are_recognised(text):
    # Every one of these was produced from non-speech: in the benchmark, or
    # (the Indonesian one) in a live session, where Halcyon then answered it.
    assert is_phantom(text)


@pytest.mark.parametrize("text", [
    "Thank you, now open the folder.",  # contains a phantom, but is a real request
    "You can stop now.",
    "Teşekkür ederim, devam et.",
    "",
])
def test_real_requests_are_not_mistaken_for_phantoms(text):
    assert not is_phantom(text)


def test_a_phantom_transcript_is_dropped_and_says_why():
    fake = FakeWhisper({None: ("Thank you.", Info("en", 0.9, [("en", 0.9)]))})
    result = transcriber_with(fake).transcribe(AUDIO)
    assert result.text == ""
    assert result.dropped == "phantom"
    assert result.is_empty


def test_phantom_filter_can_be_switched_off():
    fake = FakeWhisper({None: ("Thank you.", Info("en", 0.9, [("en", 0.9)]))})
    result = transcriber_with(fake, phantom_filter=False).transcribe(AUDIO)
    assert result.text == "Thank you."


# ------------------------------------------------------------ offline-first loading

class NotCached(Exception):
    pass


def test_model_is_loaded_from_the_local_cache_without_the_network(monkeypatch):
    calls = []

    class FakeWhisperModel:
        def __init__(self, name, local_files_only=False, **options):
            calls.append(local_files_only)

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeWhisperModel))
    monkeypatch.setitem(sys.modules, "huggingface_hub", types.ModuleType("huggingface_hub"))
    monkeypatch.setitem(sys.modules, "huggingface_hub.errors",
                        types.SimpleNamespace(LocalEntryNotFoundError=NotCached))

    Transcriber(STTSettings(model="base", device="cpu"))
    assert calls == [True]  # one attempt, local files only


def test_a_missing_model_is_downloaded_once_with_its_size_announced(monkeypatch, capsys):
    calls = []

    class FakeWhisperModel:
        def __init__(self, name, local_files_only=False, **options):
            calls.append(local_files_only)
            if local_files_only:
                raise NotCached(name)

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeWhisperModel))
    monkeypatch.setitem(sys.modules, "huggingface_hub", types.ModuleType("huggingface_hub"))
    monkeypatch.setitem(sys.modules, "huggingface_hub.errors",
                        types.SimpleNamespace(LocalEntryNotFoundError=NotCached))

    Transcriber(STTSettings(model="base", device="cpu"))
    assert calls == [True, False]
    assert "145 MB" in capsys.readouterr().out
