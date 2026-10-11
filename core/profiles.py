"""
Runtime profiles.

A laptop is two different machines depending on whether its discrete GPU is
switched on. Rather than degrading whichever component happens to notice
first, the whole stack picks a coherent set of models up front:

* **battery**     — iGPU / CPU only. Smaller models everywhere. The goal is
                    that Halcyon stays *usable* on battery, not that it stays
                    identical.
* **gpu-<model>-<context>** — a discrete GPU is available. Which models and
                    context length depends on the free VRAM; see core/vram.py.

The profile is resolved from detected hardware at startup and can always be
overridden, because "what the hardware can do" and "what the user wants it to
do right now" are different questions.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace

from core.hardware import Hardware, detect
from core.vram import DEFAULT_RESERVED_GIB, LADDER, PLANS_BY_NAME, Plan, choose


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
            f"profile: {self.label} ({self.name})\n"
            f"  STT : {self.stt_model} @ {self.stt_device} ({self.stt_compute})\n"
            f"  LLM : {self.llm_model}, ctx {self.llm_num_ctx}"
            f"{'' if self.llm_reasoning else ', thinking off'}\n"
            + (f"  expected first audio: ~{self.expected_first_audio_ms} ms"
               if self.expected_first_audio_ms else "  expected first audio: not measured yet")
            + (f"\n  reason: {self.reason}" if self.reason else "")
        )


BATTERY = Profile(
    name="battery",
    label="Battery",
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

# Expected first-audio latency for configurations that have actually been
# measured end to end. Other GPU configurations report "not measured yet"
# rather than an invented number.
MEASURED_FIRST_AUDIO_MS = {
    "gpu-9b-8k": 1400,   # RTX 4060 Laptop, 8 GB: 1105-1573 ms observed
}


def profile_from_plan(plan: Plan, reason: str = "") -> Profile:
    """Turn a VRAM plan into a runtime profile."""
    size = plan.llm_model.split(":")[1]
    return Profile(
        name=plan.name,
        label=f"GPU ({size} model, {plan.num_ctx // 1024}k context)",
        reason=reason,
        stt_model=plan.stt_model,
        stt_device="cuda",
        stt_compute="int8_float16",
        llm_model=plan.llm_model,
        llm_num_ctx=plan.num_ctx,
        # Small models wander when given room; keep their replies short.
        llm_num_predict=160 if size in ("2b", "4b") else 300,
        expected_first_audio_ms=MEASURED_FIRST_AUDIO_MS.get(plan.name, 0),
    )


# The configuration measured on the development machine; also a convenient
# fixed profile for tests and for forcing a known setup.
PERFORMANCE = profile_from_plan(PLANS_BY_NAME["gpu-9b-8k"])

PROFILES: dict[str, Profile] = {
    BATTERY.name: BATTERY,
    **{plan.name: profile_from_plan(plan) for plan in LADDER},
}


def resolve(hardware: Hardware | None = None, override: str | None = None,
            installed: set[str] | None = None) -> Profile:
    """
    Pick the profile this machine should run.

    ``override`` (or the ``HALCYON_PROFILE`` environment variable) wins over
    detection. ``installed`` is the set of models already pulled into Ollama;
    when given, the GPU plan only uses those, and suggests a better model if
    the card could run one.
    """
    hardware = hardware or detect()
    override = override or os.getenv("HALCYON_PROFILE")

    if override and override.strip().lower() != "auto":
        key = override.strip().lower()
        if key not in PROFILES:
            raise ValueError(
                f"Unknown profile {override!r}. Choices: auto, {', '.join(PROFILES)}"
            )
        return replace(PROFILES[key], reason="chosen manually (HALCYON_PROFILE / --profile)")

    if not hardware.cuda:
        if hardware.dgpu_disconnected:
            reason = (
                f"{hardware.dgpu_name} is installed but not connected (Code 45) - "
                "switch the GPU mode to Standard and restart"
            )
        else:
            reason = "no CUDA device found"
        return replace(BATTERY, reason=reason)

    free = hardware.vram_free_gb
    if free is None:
        free = max(0.0, hardware.vram_gb - DEFAULT_RESERVED_GIB)
        free_note = f"~{free:.1f} GB free (estimated)"
    else:
        free_note = f"{free:.1f} GB free"

    plan, best = choose(free, installed)
    if plan is None:
        if best is not None:
            reason = (f"{free_note}, but no model that fits is installed - "
                      f"pull one with: ollama pull {best.llm_model}")
        else:
            reason = f"{free_note} on {hardware.gpu_name}: too little for any GPU configuration"
        return replace(BATTERY, reason=reason)

    reason = f"{free_note} on {hardware.gpu_name}"
    if plan.estimated:
        reason += "; memory use of this model is estimated, verified after loading"
    if best is not None and best != plan:
        reason += f"; this card could run {best.name} - ollama pull {best.llm_model}"
    return profile_from_plan(plan, reason)


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
