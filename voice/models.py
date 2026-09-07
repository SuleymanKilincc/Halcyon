"""
Model resolution and download for the voice pipeline.

Piper voices are fetched from the rhasspy/piper-voices repository on
HuggingFace. faster-whisper downloads its own models on first use via
huggingface_hub, so only Piper needs handling here.
"""

from __future__ import annotations

import json
import shutil
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

PIPER_REPO = "rhasspy/piper-voices"
PIPER_BASE = f"https://huggingface.co/{PIPER_REPO}/resolve/main"


class VoiceModelError(RuntimeError):
    pass


@dataclass(frozen=True)
class PiperVoiceFiles:
    voice_id: str
    onnx: Path
    config: Path


def _split_voice_id(voice_id: str) -> tuple[str, str, str]:
    """
    Split a Piper voice id into (locale, name, quality).

    Voice ids look like ``tr_TR-dfki-medium`` or ``en_US-hfc_female-medium``.
    Locale and quality never contain a hyphen, and speaker names use
    underscores rather than hyphens, so a plain split is unambiguous.
    """
    parts = voice_id.split("-")
    if len(parts) != 3:
        raise VoiceModelError(
            f"Malformed Piper voice id {voice_id!r}; "
            "expected '<locale>-<name>-<quality>', e.g. 'tr_TR-dfki-medium'"
        )
    return parts[0], parts[1], parts[2]


def piper_remote_paths(voice_id: str) -> tuple[str, str]:
    """Return the repo-relative (onnx, config) paths for a voice id."""
    locale, name, quality = _split_voice_id(voice_id)
    family = locale.split("_")[0]
    stem = f"{family}/{locale}/{name}/{quality}/{voice_id}"
    return f"{stem}.onnx", f"{stem}.onnx.json"


def _download(url: str, dest: Path, *, label: str) -> None:
    # Carriage-return progress is for a human watching a terminal. Piped into
    # a log or a tool it produces thousands of useless lines, so only emit it
    # when stdout is actually a terminal.
    show_progress = sys.stdout.isatty()
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            with open(tmp, "wb") as handle:
                while True:
                    chunk = response.read(1 << 16)
                    if not chunk:
                        break
                    handle.write(chunk)
                    done += len(chunk)
                    if total and show_progress:
                        pct = done * 100 // total
                        print(f"\r  {label}: {pct:3d}%  ({done >> 20} / {total >> 20} MB)",
                              end="", flush=True)
            if total and show_progress:
                print()
    except Exception as exc:  # noqa: BLE001 - re-raised with context
        tmp.unlink(missing_ok=True)
        raise VoiceModelError(f"Failed to download {label} from {url}: {exc}") from exc

    # Only publish the final name once the body is complete, so an interrupted
    # download can never be mistaken for a usable model on the next run.
    tmp.replace(dest)


def ensure_piper_voice(voice_id: str, models_dir: Path) -> PiperVoiceFiles:
    """
    Make sure a Piper voice is present locally, downloading it if needed.

    Returns the paths to the .onnx weights and the .onnx.json config.
    """
    target_dir = Path(models_dir) / "piper" / voice_id
    onnx = target_dir / f"{voice_id}.onnx"
    config = target_dir / f"{voice_id}.onnx.json"

    if onnx.exists() and config.exists():
        return PiperVoiceFiles(voice_id, onnx, config)

    onnx_path, config_path = piper_remote_paths(voice_id)
    print(f"Downloading Piper voice {voice_id} ...")
    if not config.exists():
        _download(f"{PIPER_BASE}/{config_path}", config, label=f"{voice_id} config")
    if not onnx.exists():
        _download(f"{PIPER_BASE}/{onnx_path}", onnx, label=f"{voice_id} weights")

    # A config that does not parse means we downloaded an HTML error page.
    try:
        json.loads(config.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(target_dir, ignore_errors=True)
        raise VoiceModelError(
            f"Piper voice {voice_id!r} did not download correctly "
            f"(config is not valid JSON). Check that the voice id exists in {PIPER_REPO}."
        ) from exc

    return PiperVoiceFiles(voice_id, onnx, config)


def ensure_all_voices(voices: dict[str, str], models_dir: Path) -> dict[str, PiperVoiceFiles]:
    """Ensure every configured language voice is available locally."""
    return {lang: ensure_piper_voice(vid, models_dir) for lang, vid in voices.items()}


if __name__ == "__main__":
    from voice.settings import DEFAULT

    for lang, files in ensure_all_voices(DEFAULT.tts.voices, DEFAULT.models_dir).items():
        size = files.onnx.stat().st_size >> 20
        print(f"{lang}: {files.voice_id}  ({size} MB)  -> {files.onnx}")
