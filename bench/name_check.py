"""
Does the speech recogniser write the assistant's name correctly?

    python -m bench.name_check

The name is an unusual word, so the recogniser can turn it into other words
("calcium", "Hal John"). This measures how often it comes out right with and
without the recogniser's hotword hint, on synthesised speech (no microphone),
clean and with room noise. It is a small check - a handful of sentences, one
synthetic voice - meant to show whether the hint matters and whether the name
can be trusted as text, not to give a precise rate.
"""

from __future__ import annotations

import re
import sys
from dataclasses import replace

from bench.stt_eval import add_noise, rng_for, room_reverb, speech_clip
from voice.settings import STTSettings
from voice.stt import Transcriber
from voice.tts import Synthesizer

SENTENCES = [
    ("en", "Halcyon, what is on my desktop?"),
    ("en", "Hey Halcyon, how hot is my graphics card?"),
    ("en", "Halcyon, search the web for the latest Python release."),
    ("en", "Thanks, Halcyon."),
    ("tr", "Halcyon, masaüstümde neler var?"),
    ("tr", "Hey Halcyon, ekran kartımın sıcaklığı kaç derece?"),
]
CONDITIONS = ["clean", "noisy"]  # noisy: reverberation + noise at 10 dB SNR
NAME = re.compile(r"\bhalcyon\b", re.IGNORECASE)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    synth = Synthesizer()
    results = {}
    for label, hotwords in (("with hotword", STTSettings().hotwords), ("without hotword", None)):
        transcriber = Transcriber(replace(STTSettings(), hotwords=hotwords))
        hits = total = 0
        print(f"\n=== {label} ===")
        for language, text in SENTENCES:
            for condition in CONDITIONS:
                audio = speech_clip(synth, text, language)
                if condition == "noisy":
                    rng = rng_for("name", text, condition)
                    audio = add_noise(room_reverb(audio, rng), 10, rng)
                heard = transcriber.transcribe(audio).text
                ok = bool(NAME.search(heard))
                hits, total = hits + ok, total + 1
                print(f"  [{'ok  ' if ok else 'MISS'}] {condition:5} {language}  {text!r} -> {heard!r}")
        results[label] = (hits, total)
    print()
    for label, (hits, total) in results.items():
        print(f"{label}: name written correctly in {hits}/{total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
