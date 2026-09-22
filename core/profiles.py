"""
Runtime profiles.

A laptop is two different machines depending on whether its discrete GPU is
switched on. Rather than degrading whichever component happens to notice
first, the whole stack picks a coherent set of models up front:

* **battery**     — iGPU / CPU only. Smaller models everywhere. The goal is
                    that Jarvis stays *usable* on battery, not that it stays
                    identical.
* **performance** — discrete GPU available. Full-size STT and the 9B model.

The profile is resolved from detected hardware at startup and can always be
overridden, because "what the hardware can do" and "what the user wants it to
do right now" are different questions.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace

from core.hardware import Hardware, detect


@dataclass(frozen=True)
class Profile:
    name: str
    label: str
    reason: str = ""

    # --- speech to text
    stt_model: str = "base"
    stt_device: str = "cpu"
    stt_compute: str = "int8"

    # --- language model
    llm_model: str = "qwen3.5:4b"
    llm_num_ctx: int = 4096
    llm_num_predict: int = 200
    llm_reasoning: bool = False       # thinking tokens are pure latency in speech

    # --- what to expect, so a slow turn can be recognised as normal or not
    expected_first_audio_ms: int = 0

    def describe(self) -> str:
        return (
            f"profil: {self.label} ({self.name})\n"
            f"  STT : {self.stt_model} @ {self.stt_device} ({self.stt_compute})\n"
            f"  LLM : {self.llm_model}, ctx {self.llm_num_ctx}"
            f"{'' if self.llm_reasoning else ', thinking kapali'}\n"
            f"  beklenen ilk ses: ~{self.expected_first_audio_ms} ms"
            + (f"\n  sebep: {self.reason}" if self.reason else "")
        )


BATTERY = Profile(
    name="battery",
    label="Pil modu",
    stt_model="base",
    stt_device="cpu",
    stt_compute="int8",
    # Measured on this CPU, warm, fresh prompt (no KV cache hit):
    #   qwen3.5:4b  first token ~1600 ms, 13 tok/s
    #   qwen3.5:2b  first token ~1000 ms, 19 tok/s
    # Battery mode is explicitly a compromise, and on a voice turn the smaller
    # model's speed is worth more than its accuracy.
    llm_model="qwen3.5:2b",
    llm_num_ctx=4096,
    # Bounds the cost of an interrupted generation: the server keeps producing
    # to this limit even after the client stops reading (see core/llm.py).
    llm_num_predict=100,
    expected_first_audio_ms=2800,
)

PERFORMANCE = Profile(
    name="performance",
    label="Tam guc",
    stt_model="large-v3-turbo",
    stt_device="cuda",
    stt_compute="int8_float16",
    llm_model="qwen3.5:9b",
    # Measured on the 8 GB RTX 4060, via `ollama ps` after loading the model:
    #   ctx  8192 -> 100% GPU
    #   ctx 12288 ->  86% GPU / 14% CPU
    #   ctx 16384 ->  84% GPU / 16% CPU
    # Any spill puts transformer layers on the CPU and drags the whole
    # generation down to CPU speed, so the largest context that still fits
    # entirely in VRAM beats a nominally bigger one. 8k is ample for speech.
    # (262144, the model's maximum, is a capability figure, not a runtime one.)
    llm_num_ctx=8192,
    llm_num_predict=300,
    # Measured on the RTX 4060 once warm: STT 234-377 ms, first token
    # 114-134 ms, first audio 1105-1573 ms. The 900 ms here was a guess before
    # the GPU was available; this is the observed figure.
    expected_first_audio_ms=1400,
)

# A discrete GPU too small to hold the 9B weights plus a KV cache plus Whisper.
# Keeps the fast STT, drops back to the smaller language model.
PERFORMANCE_LOW_VRAM = replace(
    PERFORMANCE,
    name="performance-lowvram",
    label="Tam guc (dusuk VRAM)",
    llm_model="qwen3.5:4b",
    llm_num_ctx=8192,
    expected_first_audio_ms=700,
)

PROFILES: dict[str, Profile] = {
    p.name: p for p in (BATTERY, PERFORMANCE, PERFORMANCE_LOW_VRAM)
}

# Below this, the 9B model and a Whisper checkpoint cannot share the card.
MIN_VRAM_FOR_9B_GB = 7.0


def resolve(hardware: Hardware | None = None, override: str | None = None) -> Profile:
    """
    Pick the profile this machine should run.

    ``override`` (or the ``JARVIS_PROFILE`` environment variable) wins over
    detection, so a user on mains power who wants the quiet, cool machine can
    have it, and a debugging session can force either path.
    """
    hardware = hardware or detect()
    override = override or os.getenv("JARVIS_PROFILE")

    if override:
        key = override.strip().lower()
        if key not in PROFILES:
            raise ValueError(
                f"Bilinmeyen profil {override!r}. Secenekler: {', '.join(PROFILES)}"
            )
        chosen = PROFILES[key]
        return replace(chosen, reason="elle secildi (JARVIS_PROFILE / --profile)")

    if not hardware.cuda:
        if hardware.dgpu_disconnected:
            reason = (
                f"{hardware.dgpu_name} sistemde var ama bagli degil (Kod 45) - "
                "G-Helper'da Standard moda gecip yeniden baslatin"
            )
        else:
            reason = "CUDA cihazi bulunamadi"
        return replace(BATTERY, reason=reason)

    if hardware.vram_gb < MIN_VRAM_FOR_9B_GB:
        return replace(
            PERFORMANCE_LOW_VRAM,
            reason=f"{hardware.vram_gb:.1f} GB VRAM, 9B icin dar",
        )

    return replace(PERFORMANCE, reason=f"{hardware.gpu_name} kullanilabilir")


def apply_to_voice_settings(profile: Profile, settings=None, hardware=None):  # noqa: ANN001
    """
    Push a profile's STT choices into a ``VoiceSettings`` instance.

    Mutates and returns the settings object so callers can keep using the
    module-level default rather than threading a new one everywhere.
    """
    from voice.settings import DEFAULT

    settings = settings or DEFAULT
    hardware = hardware or detect(probe_dgpu=False)

    settings.stt.model = profile.stt_model
    settings.stt.device = profile.stt_device
    settings.stt.compute_type_cpu = profile.stt_compute
    settings.stt.compute_type_cuda = profile.stt_compute
    if hardware.cpu_physical:
        settings.stt.cpu_threads = hardware.cpu_physical
    return settings


if __name__ == "__main__":
    hw = detect()
    print(hw.summary())
    print()
    print(resolve(hw).describe())
