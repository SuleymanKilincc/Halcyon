"""
Speech-recognition quality benchmark: word error rate, language detection and
hallucinations, without a microphone.

    python -m bench.stt_eval                        # current settings
    python -m bench.stt_eval --set beam_size=5      # try a setting
    python -m bench.stt_eval --model small --device cpu

Speech is synthesised with Piper, so every run hears exactly the same audio
and two settings can be compared fairly. Three listening conditions:

* clean   - the synthesised speech as is
* far     - room reverberation, quieter, steady background noise at 10 dB SNR
            (someone talking across the room rather than into the microphone)
* noisy   - the same at 3 dB SNR

Plus a set of clips containing no speech at all (room noise, keyboard clicks,
breathing, mains hum). Any text produced for those is a hallucination - the
"you" that appeared in a live session came from exactly this kind of audio.

Limits, stated plainly: one synthetic voice per language is far easier than
real people, so absolute error rates are optimistic. The benchmark is for
comparing settings against each other, not for quoting accuracy.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import replace
import statistics
import sys
import zlib

import numpy as np

from bench.latency import resample
from voice.settings import DEFAULT, SAMPLE_RATE, STTSettings
from voice.stt import Transcriber
from voice.tts import Synthesizer

SENTENCES = {
    # Speech data: Turkish sentences stay Turkish, with full diacritics.
    "tr": [
        "Masaüstündeki klasörleri listeler misin",
        "Bilgisayarımın sıcaklığı kaç derece",
        "Bana kısa bir Python betiği yaz",
        "Bugün hava nasıl olacak",
        "Son indirdiğim dosyayı aç",
        "Ekran kartının bellek kullanımını göster",
        "Yarın sabah için bir hatırlatıcı kur",
        "Bu klasördeki resimleri yeni bir klasöre taşı",
        "Müzik sesini biraz kıs",
        "İnternette yapay zeka haberlerini ara",
    ],
    "en": [
        "List the folders on my desktop",
        "What is the temperature of my computer",
        "Write me a short Python script",
        "What will the weather be like today",
        "Open the last file I downloaded",
        "Show the memory usage of the graphics card",
        "Set a reminder for tomorrow morning",
        "Move the pictures in this folder to a new folder",
        "Turn the music down a little",
        "Search the web for artificial intelligence news",
    ],
}

def rng_for(*parts: str) -> np.random.Generator:
    """
    A random generator seeded by the clip's identity.

    Each clip must hear exactly the same noise in every run, whatever order
    the clips are generated in - otherwise two settings are compared on
    different audio. (A single shared generator did exactly that: the noisy
    Turkish results changed between runs just because clips were produced in
    a different order.)
    """
    return np.random.default_rng(zlib.crc32("|".join(parts).encode("utf-8")))


# ---------------------------------------------------------------- audio

def pink_noise(n: int, rng: np.random.Generator) -> np.ndarray:
    """1/f noise, closer to real room noise than white noise."""
    spectrum = np.fft.rfft(rng.standard_normal(n))
    freqs = np.fft.rfftfreq(n)
    freqs[0] = freqs[1]
    noise = np.fft.irfft(spectrum / np.sqrt(freqs), n)
    return (noise / np.max(np.abs(noise))).astype(np.float32)


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x)))) or 1e-9


def room_reverb(x: np.ndarray, rng: np.random.Generator, rt60: float = 0.5) -> np.ndarray:
    """Convolve with a synthetic room impulse response (exponentially decaying noise)."""
    t = np.arange(int(rt60 * SAMPLE_RATE)) / SAMPLE_RATE
    ir = rng.standard_normal(len(t)) * np.exp(-6.9 * t / rt60)
    ir[0] = 1.0  # direct sound
    n = len(x) + len(ir) - 1
    wet = np.fft.irfft(np.fft.rfft(x, n) * np.fft.rfft(ir, n), n)[: len(x)]
    return (wet / np.max(np.abs(wet)) * np.max(np.abs(x))).astype(np.float32)


def add_noise(speech: np.ndarray, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    noise = pink_noise(len(speech), rng)
    noise *= rms(speech) / rms(noise) / (10 ** (snr_db / 20))
    return (speech + noise).astype(np.float32)


def speech_clip(synth: Synthesizer, text: str, language: str) -> np.ndarray:
    audio = synth.synthesize_all(text, language).astype(np.float32) / 32768.0
    audio = resample(audio, synth.sample_rate, SAMPLE_RATE)
    pad = np.zeros(int(0.3 * SAMPLE_RATE), dtype=np.float32)  # VAD pre-roll/tail
    return np.concatenate([pad, audio, pad])


CONDITIONS = {
    "clean": lambda x, rng: x,
    "far": lambda x, rng: add_noise(room_reverb(x, rng) * 0.3, snr_db=10, rng=rng),
    "noisy": lambda x, rng: add_noise(room_reverb(x, rng) * 0.3, snr_db=3, rng=rng),
}


def non_speech_clips() -> dict[str, np.ndarray]:
    n = 2 * SAMPLE_RATE
    r = {name: rng_for("non-speech", name) for name in
         ("near silence", "room noise", "keyboard", "breathing", "mains hum")}
    clicks = np.zeros(n, dtype=np.float32)
    for start in r["keyboard"].integers(0, n - 400, 14):  # keyboard: sharp decaying ticks
        clicks[start:start + 400] += (r["keyboard"].standard_normal(400) * np.exp(-np.arange(400) / 40)).astype(np.float32) * 0.3
    breath = pink_noise(n, r["breathing"]) * 0.05
    breath *= (np.sin(np.linspace(0, 3 * np.pi, n)) ** 2).astype(np.float32)  # in-out envelope
    t = np.arange(n) / SAMPLE_RATE
    hum = (0.02 * np.sin(2 * np.pi * 50 * t) + 0.01 * np.sin(2 * np.pi * 150 * t)).astype(np.float32)
    return {
        "near silence": pink_noise(n, r["near silence"]) * 0.003,
        "room noise": pink_noise(n, r["room noise"]) * 0.03,
        "keyboard": clicks + pink_noise(n, r["keyboard"]) * 0.003,
        "breathing": breath,
        "mains hum": hum + pink_noise(n, r["mains hum"]) * 0.003,
    }


# ---------------------------------------------------------------- scoring

def normalise(text: str, language: str) -> list[str]:
    if language == "tr":
        # Turkish casing: I -> ı and İ -> i, which str.lower() gets wrong.
        text = text.replace("I", "ı").replace("İ", "i")
    text = text.lower().replace("'", "").replace("’", "")
    text = re.sub(r"[^\w\s]", " ", text)
    return text.split()


def word_errors(reference: list[str], hypothesis: list[str]) -> int:
    """Levenshtein distance over words: substitutions + insertions + deletions."""
    previous = list(range(len(hypothesis) + 1))
    for i, ref_word in enumerate(reference, 1):
        current = [i] + [0] * len(hypothesis)
        for j, hyp_word in enumerate(hypothesis, 1):
            current[j] = min(previous[j] + 1, current[j - 1] + 1,
                             previous[j - 1] + (ref_word != hyp_word))
        previous = current
    return previous[-1]


# ---------------------------------------------------------------- run

def parse_overrides(pairs: list[str]) -> dict:
    out = {}
    for pair in pairs:
        key, _, value = pair.partition("=")
        if value.lower() in ("true", "false"):
            out[key] = value.lower() == "true"
        else:
            try:
                out[key] = int(value)
            except ValueError:
                try:
                    out[key] = float(value)
                except ValueError:
                    out[key] = value
    return out


# Settings compared by --compare, in the order they were adopted. Each row adds
# one change to the row above, so every difference is attributable to it.
COMPARE = [
    ("before", dict(drop_other_languages=False, vad_filter=False,
                    phantom_filter=False, hotwords=None)),
    ("+ second-stage VAD", dict(drop_other_languages=False, vad_filter=True,
                                phantom_filter=False, hotwords=None)),
    ("+ phantom filter", dict(drop_other_languages=False, vad_filter=True,
                              phantom_filter=True, hotwords=None)),
    ("+ hotwords", dict(drop_other_languages=False)),
    ("+ drop other languages", {}),
    ("default, beam 5", dict(beam_size=5)),
]


def build_clips(synth: Synthesizer, draws: int):
    clips = []  # (condition, language, sentence, audio)
    for condition, degrade in CONDITIONS.items():
        n = 1 if condition == "clean" else draws
        for language, sentences in SENTENCES.items():
            for sentence in sentences:
                raw = speech_clip(synth, sentence, language)
                for draw in range(n):
                    clips.append((condition, language, sentence,
                                  degrade(raw, rng_for(condition, language, sentence, str(draw)))))
    return clips


def evaluate(transcriber: Transcriber, clips, noise, show: bool = False) -> dict:
    import ctranslate2

    cells: dict = {}
    latencies = []
    for index, (condition, language, sentence, audio) in enumerate(clips):
        # On very noisy audio Whisper retries with random sampling
        # ("temperature fallback"), so the same clip could decode differently
        # on every run - by 10+ points of error rate in the noisy column.
        # Seeding the sampler per clip makes the whole table reproducible.
        ctranslate2.set_random_seed(index)
        result = transcriber.transcribe(audio)
        latencies.append(result.latency_ms)
        ref, hyp = normalise(sentence, language), normalise(result.text, language)
        cell = cells.setdefault((condition, language), {"errors": 0, "words": 0, "detected": 0, "clips": 0})
        cell["errors"] += word_errors(ref, hyp)
        cell["words"] += len(ref)
        cell["clips"] += 1
        # The raw detection, not the final label: the label is a candidate
        # language by construction, so counting it would hide every wrong
        # detection (it did, once).
        cell["detected"] += result.detected_language == language
        if show and ref != hyp:
            print(f"      [{result.detected_language}->{result.language}] {result.text!r}  <- {sentence!r}")
    phantoms = {}
    for index, (name, audio) in enumerate(noise.items()):
        ctranslate2.set_random_seed(10_000 + index)
        result = transcriber.transcribe(audio)
        latencies.append(result.latency_ms)
        phantoms[name] = result.text.strip() or (f"- (dropped: {result.dropped})" if result.dropped else "-")
    return {"cells": cells, "phantoms": phantoms,
            "hallucinated": sum(not v.startswith("-") for v in phantoms.values()),
            "latency_ms": statistics.median(latencies)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="large-v3-turbo")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--set", action="append", default=[], metavar="FIELD=VALUE",
                        help="override an STTSettings field, e.g. beam_size=5")
    parser.add_argument("--draws", type=int, default=3,
                        help="noise draws per sentence in the degraded conditions (default 3)")
    parser.add_argument("--compare", action="store_true",
                        help="run the adopted changes one by one on identical audio")
    parser.add_argument("--show", action="store_true", help="print every transcript")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    settings = STTSettings(model=args.model, device=args.device)
    for key, value in parse_overrides(args.set).items():
        if not hasattr(settings, key):
            parser.error(f"STTSettings has no field {key!r}")
        setattr(settings, key, value)

    transcriber = Transcriber(settings)
    transcriber.warmup()

    # Piper's default synthesis is random on purpose (noise_scale/noise_w make
    # the voice less robotic): the same sentence comes out slightly different
    # every time, so two runs would not hear the same audio. Switching the
    # randomness off makes the test audio identical across runs and machines.
    synth = Synthesizer(replace(DEFAULT.tts, noise_scale=0.0, noise_w=0.0), DEFAULT.models_dir)
    synth.preload()
    clips = build_clips(synth, args.draws)
    noise = non_speech_clips()
    print(f"{transcriber.describe()}  |  {len(clips)} speech clips, {len(noise)} non-speech\n")

    if args.compare:
        header = (f"{'settings':<24}" + "".join(f"{c[:5] + '-' + l:>10}" for c in CONDITIONS for l in SENTENCES)
                  + f"{'phantoms':>10}{'ms':>6}")
        print(header)
        print("-" * len(header))
        for name, overrides in COMPARE:
            transcriber.settings = replace(settings, **overrides)
            r = evaluate(transcriber, clips, noise)
            row = "".join(f"{r['cells'][(c, l)]['errors'] / r['cells'][(c, l)]['words']:>10.1%}"
                          for c in CONDITIONS for l in SENTENCES)
            print(f"{name:<24}{row}{r['hallucinated']:>7}/{len(noise)}{r['latency_ms']:>6.0f}")
        words = {k: v["words"] for k, v in r["cells"].items()}
        print("\nwords per column: " + ", ".join(f"{c}-{l}={n}" for (c, l), n in words.items()))
        return 0

    r = evaluate(transcriber, clips, noise, show=args.show)
    print(f"{'condition':<8} {'lang':<5} {'WER':>6} {'detected ok':>12}")
    for (condition, language), cell in r["cells"].items():
        print(f"{condition:<8} {language:<5} {cell['errors'] / cell['words']:>6.1%} "
              f"{cell['detected']:>9}/{cell['clips']:<4}  ({cell['words']} words)")
    print("\nNon-speech clips (any text here is a hallucination):")
    for name, shown in r["phantoms"].items():
        print(f"  {name:<13} {shown}")
    print(f"  hallucinated on {r['hallucinated']} of {len(noise)}")
    print(f"\nlatency per utterance: median {r['latency_ms']:.0f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
