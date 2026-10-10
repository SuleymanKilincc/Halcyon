"""
Tests for turn endpointing (voice/vad.py).

The real detector asks the Silero neural network "is this frame speech?". Here
that answer is scripted instead, which isolates the part worth testing: the
state machine that turns per-frame yes/no into "the user started" and "the
user finished". The network is someone else's code; the turn logic is ours.
"""

import sys
import types

import numpy as np
import pytest

from voice.settings import VAD_FRAME_MS, VAD_FRAME_SAMPLES, VADSettings
from voice.vad import SpeechDetector, VADEvent

SPEECH, SILENCE = 0.9, 0.1


@pytest.fixture
def make_detector(monkeypatch):
    # SpeechDetector imports silero_vad (which pulls in PyTorch) inside its
    # constructor. Putting a stand-in module in sys.modules first means the
    # test needs neither, and runs in milliseconds on a machine with no GPU.
    fake = types.ModuleType("silero_vad")
    fake.load_silero_vad = lambda: object()
    monkeypatch.setitem(sys.modules, "silero_vad", fake)

    def build(**overrides):
        values = dict(threshold=0.5, min_speech_ms=160, min_silence_ms=480,
                      pre_roll_ms=320, max_utterance_ms=30_000)
        values.update(overrides)
        return SpeechDetector(VADSettings(**values))

    return build


@pytest.fixture
def detector(make_detector):
    return make_detector()


def run(detector: SpeechDetector, probabilities: list[float]):
    """Feed one scripted probability per frame; return (events, utterance)."""
    script = iter(probabilities)
    detector.probability = lambda frame: next(script)
    frame = np.zeros(VAD_FRAME_SAMPLES, dtype=np.int16)

    events, utterance = [], None
    for _ in probabilities:
        event, maybe = detector.push(frame)
        if event is not VADEvent.NONE:
            events.append(event)
        if maybe is not None:
            utterance = maybe
    return events, utterance


def frames(ms: int) -> int:
    return ms // VAD_FRAME_MS


def test_silence_never_starts_a_turn(detector):
    events, utterance = run(detector, [SILENCE] * 100)
    assert events == []
    assert utterance is None


def test_a_cough_is_too_short_to_count_as_speech(detector):
    # 3 frames = 96 ms, below the 160 ms minimum.
    events, _ = run(detector, [SILENCE] * 10 + [SPEECH] * 3 + [SILENCE] * 30)
    assert events == []


def test_a_real_utterance_starts_and_ends(detector):
    probs = [SILENCE] * 20 + [SPEECH] * 30 + [SILENCE] * 20
    events, utterance = run(detector, probs)
    assert events == [VADEvent.SPEECH_START, VADEvent.SPEECH_END]
    assert utterance is not None


def test_utterance_keeps_pre_roll_and_drops_trailing_silence(detector):
    # 30 speech frames, preceded by silence. Start fires on the 5th speech
    # frame, and the 320 ms (10-frame) pre-roll window at that moment holds
    # 5 silence + 5 speech frames, so the first syllable is not clipped. The
    # 15 silence frames that ended the turn are trimmed off again.
    # Expected: 5 pre-roll silence + 30 speech = 35 frames.
    probs = [SILENCE] * 20 + [SPEECH] * 30 + [SILENCE] * 20
    _, utterance = run(detector, probs)
    assert len(utterance.audio) == 35 * VAD_FRAME_SAMPLES
    assert utterance.duration_ms == 35 * VAD_FRAME_MS


def test_a_short_pause_mid_sentence_does_not_end_the_turn(detector):
    # A 320 ms breath between words is shorter than the 480 ms needed to end
    # the turn, so it stays one utterance.
    pause = [SILENCE] * frames(320)
    probs = [SPEECH] * 20 + pause + [SPEECH] * 20 + [SILENCE] * 20
    events, _ = run(detector, probs)
    assert events == [VADEvent.SPEECH_START, VADEvent.SPEECH_END]


def test_endless_speech_is_cut_at_the_maximum_length(make_detector):
    detector = make_detector(max_utterance_ms=1_000)
    events, utterance = run(detector, [SPEECH] * 200)
    assert VADEvent.SPEECH_END in events
    assert utterance.duration_ms <= 1_000 + VAD_FRAME_MS


def test_wrong_frame_size_is_rejected(detector):
    # Silero only accepts exactly 512 samples at 16 kHz; anything else must
    # fail loudly rather than produce garbage probabilities. This calls the
    # real probability() method, not the scripted one used above.
    with pytest.raises(ValueError):
        detector.probability(np.zeros(400, dtype=np.int16))
