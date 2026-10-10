"""
Voice pipeline latency benchmark.

Runs without a microphone: a sentence is synthesised with Piper, resampled to
16 kHz and fed through the real VAD and the real Whisper model, so every stage
except the physical audio device is measured end to end.

    python -m bench.latency                        # audio path only (no LLM)
    python -m bench.latency --llm                  # include a streaming LLM round trip
    python -m bench.latency --llm --profile battery

The number to watch is *first audio*: how long after the user stops speaking
until they hear the first sound back. Anything under ~1.5 s reads as
conversation; past ~2.5 s it reads as a form submission.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time

import numpy as np

from core.hardware import detect
from core.llm import build_llm, check_model_available, stream_reply
from core.profiles import PROFILES, apply_to_voice_settings, resolve
from voice.settings import DEFAULT, SAMPLE_RATE
from voice.stt import Transcriber
from voice.tts import SentenceStreamer, Synthesizer
from voice.vad import SpeechDetector, VADEvent

# Test utterances are speech *data*, so the Turkish ones stay Turkish - and
# they must keep their diacritics: without them Piper mispronounces the words
# and the STT measurement is scored on speech that was never correct.
PROMPTS = [
    ("tr", "Masaüstündeki dosyaları listeler misin"),
    ("tr", "Bana kısa bir Python betiği yaz"),
    ("tr", "Sistem sıcaklığı nedir"),
    ("en", "List the files on my desktop"),
]

# A scripted Turkish reply (spoken data), used when no LLM is involved so that
# synthesis timing is measured on realistic text.
REPLY = (
    "Tabii efendim. Masaüstünüzdeki dosyaları listeledim. "
    "Toplam on iki dosya var, bunların üçü klasör. "
    "Ayrıntılı görmek ister misiniz?"
)


def resample(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    """Linear resample. Good enough for a benchmark fixture, not for production."""
    if source_rate == target_rate:
        return audio.astype(np.float32)
    duration = len(audio) / source_rate
    target_len = int(duration * target_rate)
    source_x = np.linspace(0.0, duration, num=len(audio), endpoint=False)
    target_x = np.linspace(0.0, duration, num=target_len, endpoint=False)
    return np.interp(target_x, source_x, audio.astype(np.float32)).astype(np.float32)


def make_utterance(synth: Synthesizer, text: str, language: str) -> np.ndarray:
    """Produce 16 kHz float32 audio of someone saying ``text``."""
    audio = synth.synthesize_all(text, language)
    mono = audio.astype(np.float32) / 32768.0
    resampled = resample(mono, synth.sample_rate, SAMPLE_RATE)
    # Pad with silence so the VAD sees a real turn boundary rather than audio
    # that starts and ends abruptly at the buffer edges.
    pad = np.zeros(int(SAMPLE_RATE * 0.7), dtype=np.float32)
    return np.concatenate([pad, resampled, pad])


def run_vad(detector: SpeechDetector, audio: np.ndarray) -> tuple[np.ndarray | None, int]:
    """Feed audio through the VAD; return the endpointed utterance and its frame count."""
    from voice.settings import VAD_FRAME_SAMPLES

    detector.reset()
    frames = 0
    for start in range(0, len(audio) - VAD_FRAME_SAMPLES + 1, VAD_FRAME_SAMPLES):
        frames += 1
        event, utterance = detector.push(audio[start:start + VAD_FRAME_SAMPLES])
        if event is VADEvent.SPEECH_END and utterance is not None:
            return utterance.audio, frames
    return None, frames


def scripted_stream(reply: str, delta_delay: float = 0.02):
    """A stand-in for the LLM that streams at a plausible token rate."""
    for word in reply.split(" "):
        time.sleep(delta_delay)
        yield word + " "


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llm", action="store_true", help="use a real LLM round trip")
    parser.add_argument("--profile", default=None, choices=sorted(PROFILES),
                        help="override hardware detection")
    parser.add_argument("--model", default=None, help="override just the LLM model name")
    parser.add_argument("--runs", type=int, default=1, help="repeat each prompt N times")
    args = parser.parse_args()

    print("=" * 72)
    print("JARVIS VOICE LATENCY BENCHMARK")
    print("=" * 72)

    hardware = detect()
    profile = resolve(hardware, args.profile)
    if args.model:
        from dataclasses import replace as _replace

        profile = _replace(profile, llm_model=args.model)
    print()
    print(hardware.summary())
    print()
    print(profile.describe())

    settings = apply_to_voice_settings(profile, DEFAULT, hardware)

    if args.llm:
        available, problem = check_model_available(profile)
        if not available:
            print()
            print(f"ERROR: {problem}")
            return 1

    load_start = time.perf_counter()
    transcriber = Transcriber(settings.stt)
    synth = Synthesizer(settings.tts, settings.models_dir)
    synth.preload()
    detector = SpeechDetector(settings.vad)
    transcriber.warmup()
    synth.synthesize_all("warm-up", "en")
    print(f"\nSTT : {transcriber.describe()}")
    print(f"TTS : piper {settings.tts.voices} @ {synth.sample_rate} Hz")
    print(f"VAD : silero, {settings.vad.min_silence_ms} ms endpoint silence")
    print(f"Cold start (all models loaded + warmed): {time.perf_counter() - load_start:.1f} s\n")

    llm = build_llm(profile) if args.llm else None

    totals: list[int] = []
    header = f"{'lang':<5} {'prompt':<38} {'STT':>7} {'LLM-1st':>9} {'TTS':>7} {'TOTAL':>8}"
    print(header)
    print("-" * len(header))

    for language, prompt in PROMPTS:
        for _ in range(args.runs):
            spoken = make_utterance(synth, prompt, language)
            utterance, _ = run_vad(detector, spoken)
            if utterance is None:
                print(f"{language:<5} {prompt[:38]:<38}   VAD did not detect a turn")
                continue

            # Everything from here is on the user-visible latency path.
            speech_end = time.perf_counter()
            transcript = transcriber.transcribe(utterance, language=language)
            transcribed = time.perf_counter()

            streamer = SentenceStreamer(settings.tts.min_sentence_chars)
            first_token = 0.0
            first_audio = 0.0
            source = (
                stream_reply(llm, transcript.text or prompt)
                if args.llm else scripted_stream(REPLY)
            )
            try:
                for delta in source:
                    if not first_token:
                        first_token = time.perf_counter()
                    for sentence in streamer.push(delta):
                        if not first_audio:
                            synth.synthesize_all(sentence, language)
                            first_audio = time.perf_counter()
                            break
                    if first_audio:
                        break
                if not first_audio:
                    for sentence in streamer.flush():
                        synth.synthesize_all(sentence, language)
                        first_audio = time.perf_counter()
                        break
                # Drain the rest AFTER the clock has stopped. The timings above
                # are already recorded, so this costs nothing measured - but
                # leaving the stream unfinished makes the server keep
                # generating, and the next iteration then measures its own
                # queueing rather than the model. That artefact is what made
                # every row report a near-identical ~3.7 s.
                for _ in source:
                    pass
            except Exception as exc:  # noqa: BLE001
                print(f"{language:<5} {prompt[:38]:<38}   LLM error: {exc}")
                continue
            finally:
                close = getattr(source, "close", None)
                if close is not None:
                    close()

            stt_ms = round((transcribed - speech_end) * 1000)
            llm_ms = round((first_token - transcribed) * 1000)
            tts_ms = round((first_audio - first_token) * 1000)
            total_ms = round((first_audio - speech_end) * 1000)
            totals.append(total_ms)

            print(f"{language:<5} {prompt[:38]:<38} {stt_ms:>6}ms {llm_ms:>8}ms "
                  f"{tts_ms:>6}ms {total_ms:>7}ms")
            if transcript.text.strip().lower() != prompt.strip().lower():
                print(f"      heard: {transcript.text.strip()!r}")

    if totals:
        print("-" * len(header))
        print(f"first audio  median {statistics.median(totals):.0f} ms   "
              f"min {min(totals)} ms   max {max(totals)} ms")
        target = profile.expected_first_audio_ms if args.llm else 1500
        verdict = "PASS" if statistics.median(totals) <= target else "OVER BUDGET"
        print(f"target <= {target} ms ({profile.label})  ->  {verdict}")
        if not args.llm:
            print("\nNote: run with --llm for the real figure; the scripted stream "
                  "does not include model thinking time.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
