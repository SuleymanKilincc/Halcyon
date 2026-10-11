"""
Live voice loop, on the terminal.

    python -m voice.cli                       # echo mode: no LLM, audio path only
    python -m voice.cli --llm                 # talk to the model for this profile
    python -m voice.cli --llm --profile battery
    python -m voice.cli --devices             # list audio devices and exit
    python -m voice.cli --info                # show detected hardware + profile
    python -m voice.cli --llm --input 1 --output 11

Just talk. There is no button: the VAD decides when you started and stopped.
You can interrupt Halcyon mid-sentence by talking over it.

The profile (which STT and LLM models get loaded) is chosen from the detected
hardware unless --profile says otherwise. See core/profiles.py.

Headphones are strongly recommended. Without them the microphone hears the
speakers, and barge-in has to be made deliberately hard to trigger to
compensate, which makes it less responsive to you as well.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterator

from core.hardware import detect
from core.fit import fit_to_gpu
from core.llm import build_llm, check_model_available, installed_models, stream_reply
from core.profiles import PROFILES, apply_to_voice_settings, resolve
from core.voice_tools import describe_voice_tools, get_voice_tools
from voice.pipeline import State, TurnTimings, VoiceEvents, VoiceLoop
from voice.settings import DEFAULT
from voice.stt import Transcript

STATE_LABEL = {
    State.IDLE: "",
    State.LISTENING: "listening",
    State.TRANSCRIBING: "transcribing",
    State.RESPONDING: "thinking",
    State.SPEAKING: "speaking",
}


# What echo mode says back, per detected language. These are spoken words,
# so they stay in the language the user spoke.
ECHO_PREFIX = {"tr": "Şunu duydum:", "en": "I heard:"}


def make_echo_handler():
    def handler(transcript: Transcript) -> Iterator[str]:
        prefix = ECHO_PREFIX.get(transcript.language, ECHO_PREFIX["en"])
        yield f"{prefix} {transcript.text}"

    return handler


def make_llm_handler(profile, tools):  # noqa: ANN001
    llm = build_llm(profile, tools=tools)
    # Load the weights now. Otherwise the first thing the user says pays a
    # 3.7-6.7 s cold start and it looks like the assistant is broken.
    print(f"Warming up the model ({profile.llm_model})...")
    llm.warmup()

    def handler(transcript: Transcript) -> Iterator[str]:
        yield from stream_reply(llm, transcript.text, language=transcript.language)

    return llm, handler


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--llm", action="store_true", help="use the profile's model")
    parser.add_argument("--profile", default=None, choices=sorted(PROFILES),
                        help="override hardware detection")
    parser.add_argument("--model", default=None, help="override just the LLM model name")
    parser.add_argument("--devices", action="store_true", help="list audio devices and exit")
    parser.add_argument("--info", action="store_true", help="show hardware and profile, then exit")
    parser.add_argument("--input", default=None, help="input device index or name")
    parser.add_argument("--output", default=None, help="output device index or name")
    parser.add_argument("--no-barge-in", action="store_true", help="disable interruption")
    parser.add_argument("--no-tools", action="store_true", help="disable tool calling")
    parser.add_argument("--unsafe-tools", action="store_true",
                        help="also expose the mutating tools (no approval layer yet)")
    args = parser.parse_args()

    if args.devices:
        from voice.audio import list_devices

        print(list_devices())
        return 0

    hardware = detect()
    # Only consider models that are actually pulled, so a large card does not
    # pick one that is not there (it is suggested instead).
    installed = installed_models() if args.llm else None
    profile = resolve(hardware, args.profile, installed=installed)
    if args.model:
        from dataclasses import replace

        profile = replace(profile, llm_model=args.model, reason="model chosen manually")

    print(hardware.summary())
    print()
    print(profile.describe())
    print()
    if args.info:
        return 0

    settings = apply_to_voice_settings(profile, DEFAULT, hardware)
    if args.input is not None:
        settings.input_device = int(args.input) if args.input.isdigit() else args.input
    if args.output is not None:
        settings.output_device = int(args.output) if args.output.isdigit() else args.output
    if args.no_barge_in:
        settings.barge_in.enabled = False

    llm = None
    tools = []
    if args.llm:
        available, problem = check_model_available(profile)
        if not available:
            print(f"ERROR: {problem}")
            return 1
        if not args.no_tools:
            tools = get_voice_tools(include_gated=args.unsafe_tools)
            print(f"Tools: {describe_voice_tools(include_gated=args.unsafe_tools)}")
        llm, handler = make_llm_handler(profile, tools)
        # The plan was chosen from measured sizes; confirm the card agrees.
        profile = fit_to_gpu(llm, profile, installed)
        # A step down may also have changed the speech model; Whisper is
        # loaded only after this point, so the settings can still follow.
        settings = apply_to_voice_settings(profile, settings, hardware)
    else:
        handler = make_echo_handler()

    def on_speech_start() -> None:
        # The GPU drops into a low-power state when idle and costs ~2 s to
        # wake. Firing the wake-up here means it overlaps with the user still
        # speaking rather than landing on top of their answer.
        if llm is not None:
            llm.prewarm()

    def on_state(state: State) -> None:
        label = STATE_LABEL.get(state, "")
        if label:
            print(f"\r[{label}]{' ' * 20}", end="", flush=True)

    def on_user(transcript: Transcript) -> None:
        print(f"\r\033[92mYou\033[0m ({transcript.language}): {transcript.text}")

    def on_done(text: str) -> None:
        if llm is not None and llm.last_tool_calls:
            print(f"  \033[90mtools: {', '.join(llm.last_tool_calls)}\033[0m")
        print(f"\033[96mHalcyon\033[0m: {text.strip()}")

    def on_barge_in() -> None:
        print("\r\033[93m-- interrupted --\033[0m")

    def on_timings(t: TurnTimings) -> None:
        over = ""
        if profile.expected_first_audio_ms and t.total_to_first_audio_ms > 0:
            ratio = t.total_to_first_audio_ms / profile.expected_first_audio_ms
            if ratio > 1.5:
                over = f"  ({ratio:.1f}x the expected time)"
        print(f"  \033[90mstt {t.stt_ms} ms | first token {t.llm_first_token_ms} ms | "
              f"tts {t.tts_ms} ms | first audio {t.total_to_first_audio_ms} ms{over}\033[0m")

    def on_error(exc: Exception) -> None:
        print(f"\r\033[91mError:\033[0m {exc}")

    events = VoiceEvents(
        on_speech_start=on_speech_start,
        on_state=on_state,
        on_user=on_user,
        on_response_done=on_done,
        on_barge_in=on_barge_in,
        on_timings=on_timings,
        on_error=on_error,
    )

    loop = VoiceLoop(handler, settings, events)
    print("Loading models...")
    loop.prepare()
    print(f"STT : {loop.transcriber.describe()}")
    print(f"TTS : {settings.tts.voices} @ {loop.synthesizer.sample_rate} Hz")
    print(f"Mode: {profile.llm_model if args.llm else 'echo (no LLM)'}"
          f"{'  | barge-in off' if args.no_barge_in else ''}")
    print("\nStart talking. Press Ctrl+C to quit.\n")

    try:
        loop.run()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        loop.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
