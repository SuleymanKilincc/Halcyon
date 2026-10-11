"""
VRAM planning: pick the best models that fit the GPU actually present.

Halcyon loads two models onto the same card - Whisper for speech recognition and
an LLM through Ollama - and the right pair depends entirely on how much memory
is free. A fixed rule cannot serve a 4 GB RTX 3050 and a 32 GB RTX 5090 at the
same time: the first overflows (layers spill to the CPU and every token slows
down), the second sits mostly idle.

The planner works in two layers:

1. **Plan** - choose from a ladder of configurations, best first, the first one
   whose measured memory fits the free VRAM.
2. **Verify** - after the LLM is loaded, ask Ollama how much of it really landed
   on the GPU, and step down the ladder if any of it spilled. Ollama keeps more
   headroom than the sizes it reports (see HEADROOM_GIB), so the plan is a
   well-informed first guess and the verification is what makes it correct on
   hardware nobody has tested.

All sizes are GiB. Re-measure with `python -m bench.vram`.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from dataclasses import dataclass

# --------------------------------------------------------------- measurements
# Measured on an RTX 4060 Laptop GPU (8 GB) with bench/vram.py.

# faster-whisper, int8_float16, after one inference (buffers allocated).
WHISPER_GIB = {
    "base": 0.19,
    "small": 0.29,
    "large-v3-turbo": 1.01,
}

# Total memory Ollama reports for the model at each context length.
LLM_GIB: dict[str, dict[int, float]] = {
    "qwen3.5:2b": {4096: 2.19, 8192: 2.30, 16384: 2.41, 32768: 2.55},
    "qwen3.5:4b": {4096: 2.91, 8192: 3.04, 16384: 3.38, 32768: 3.82},
    "qwen3.5:9b": {4096: 5.11, 8192: 5.24, 16384: 6.10, 32768: 6.74},
    # NOT measured - the 27B model (17.5 GB download) has not been pulled on
    # the development machine. Scaled from the 9B figures: weights by download
    # size (17.48 / 6.55 GB), context cost doubled. Treat as an estimate; the
    # verification step corrects it on real hardware.
    "qwen3.5:27b": {4096: 13.64, 8192: 13.90, 16384: 15.62, 32768: 16.90},
}
ESTIMATED = {"qwen3.5:27b"}

# Free VRAM that must remain after both models are counted. Ollama decides
# placement with a larger internal estimate than the size it reports, so a
# configuration can "fit" on paper and still spill. Calibrated against what
# was observed on the 8 GB card (7.07 GiB free with nothing loaded):
#   9b @ 8k with large-v3-turbo also loaded -> ran 100% on the GPU (must fit:
#       6.25 GiB, so the headroom can be at most 0.82)
#   9b @ 16k with nothing else loaded       -> spilled onto the CPU (must not
#       fit; with Whisper added it needs 7.11 GiB, rejected by any headroom)
# 0.5 satisfies both. It is a calibrated heuristic, not a law: how much Ollama
# reserves is not documented and was not fully predictable from outside, which
# is why the result is always verified after loading.
HEADROOM_GIB = 0.5

# What the desktop and other programs typically occupy when the free amount
# cannot be read directly (measured 0.83-0.92 GiB on the development machine).
DEFAULT_RESERVED_GIB = 0.9


@dataclass(frozen=True)
class Plan:
    llm_model: str
    num_ctx: int
    stt_model: str

    @property
    def name(self) -> str:
        # The speech model is part of the name whenever it is not the default
        # large one, so two plans that share a language model stay distinct.
        size = self.llm_model.split(":")[1]
        suffix = "" if self.stt_model == "large-v3-turbo" else f"-{self.stt_model}"
        return f"gpu-{size}-{self.num_ctx // 1024}k{suffix}"

    @property
    def needed_gib(self) -> float:
        return LLM_GIB[self.llm_model][self.num_ctx] + WHISPER_GIB[self.stt_model]

    @property
    def estimated(self) -> bool:
        return self.llm_model in ESTIMATED


# Best first. The order encodes priorities: a larger language model is worth
# more than a longer context (8k is ample for spoken turns), and the large
# Whisper is kept as long as possible because the smaller ones are poor at
# Turkish (on the same sentence, `base` heard "BİVİ SAYA RIM'ın" where
# large-v3-turbo heard "Bilgisayarımın").
LADDER: tuple[Plan, ...] = (
    Plan("qwen3.5:27b", 32768, "large-v3-turbo"),
    Plan("qwen3.5:27b", 16384, "large-v3-turbo"),
    Plan("qwen3.5:27b", 8192, "large-v3-turbo"),
    Plan("qwen3.5:9b", 32768, "large-v3-turbo"),
    Plan("qwen3.5:9b", 16384, "large-v3-turbo"),
    Plan("qwen3.5:9b", 8192, "large-v3-turbo"),
    Plan("qwen3.5:4b", 8192, "large-v3-turbo"),
    Plan("qwen3.5:4b", 8192, "small"),
    Plan("qwen3.5:2b", 8192, "small"),
    Plan("qwen3.5:2b", 4096, "base"),
)

PLANS_BY_NAME = {p.name: p for p in LADDER}


def fits(plan: Plan, free_gib: float) -> bool:
    return plan.needed_gib + HEADROOM_GIB <= free_gib


def choose(free_gib: float, installed: set[str] | None = None) -> tuple[Plan | None, Plan | None]:
    """
    Return (plan to use, best plan the card could run).

    `installed` limits the choice to models already pulled into Ollama, so a
    large card never selects a model that is not there. The second value is
    the best plan ignoring what is installed; when it differs, the caller can
    suggest pulling a better model. Either is None when nothing fits.
    """
    best_possible = next((p for p in LADDER if fits(p, free_gib)), None)
    if installed is None:
        return best_possible, best_possible
    usable = next((p for p in LADDER if fits(p, free_gib) and p.llm_model in installed), None)
    return usable, best_possible


def step_down(current: Plan, installed: set[str] | None = None) -> Plan | None:
    """
    The next rung below `current` whose language model is installed.

    Used after a spill. The language model is loaded and checked before
    Whisper, so the speech model can still change at that point too.
    """
    for plan in LADDER[LADDER.index(current) + 1:]:
        if installed is None or plan.llm_model in installed:
            return plan
    return None


def query_free_vram_gib() -> tuple[float, float] | None:
    """
    (free, total) GiB on GPU 0 from nvidia-smi, or None if unavailable.

    nvidia-smi is used rather than torch.cuda.mem_get_info() because the latter
    creates a CUDA context in this process, which itself occupies a few hundred
    megabytes of the memory being measured.
    """
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:  # noqa: BLE001 - absence of nvidia-smi is a normal case
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    free_mib, total_mib = (float(v) for v in out.stdout.strip().splitlines()[0].split(","))
    return free_mib / 1024, total_mib / 1024


def resident_vram_gib(payload: dict) -> float:
    """GiB of GPU memory held by the models listed in an Ollama /api/ps reply."""
    return sum(m.get("size_vram", 0) for m in payload.get("models", [])) / 2**30


def ollama_resident_gib(base_url: str | None = None, timeout: float = 2.0) -> float:
    """
    GPU memory currently held by models Ollama has loaded, 0.0 if it cannot be asked.

    Ollama keeps a model in memory for minutes after its last request. That
    memory counts as "used" in nvidia-smi, but it is not lost: Ollama reuses it
    for the same model and evicts idle models to make room for another. Counting
    it as unavailable made a restart within that window plan for the CPU. The
    placement check after loading is the safety net if this turns out optimistic.
    """
    host = base_url or os.getenv("OLLAMA_HOST") or "http://localhost:11434"
    if "://" not in host:
        host = "http://" + host
    try:
        with urllib.request.urlopen(host.rstrip("/") + "/api/ps", timeout=timeout) as reply:
            return resident_vram_gib(json.load(reply))
    except Exception:  # noqa: BLE001 - Ollama not running is a normal case
        return 0.0
