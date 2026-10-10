"""
Make sure the language model really runs on the GPU, and step down if not.

The VRAM planner (core/vram.py) chooses a configuration from measured sizes,
but how much headroom Ollama keeps for itself is not documented and was not
fully predictable from outside. So after the model is loaded, this asks
Ollama where it actually placed it. If part of it spilled onto the CPU - which
silently slows every token - the model is unloaded and the next configuration
down the ladder is tried.

This is what makes the planner safe on GPUs that were never tested: the plan
is a first guess, and the card itself confirms or corrects it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from core.profiles import Profile, profile_from_plan
from core.vram import PLANS_BY_NAME, step_down

# Ollama reports sizes rounded to whole bytes of differently-sized buffers; a
# model whose GPU share is within a hair of the total is fully on the GPU.
FULLY_ON_GPU = 0.99


class Placeable(Protocol):
    def placement(self) -> tuple[float, float] | None: ...
    def unload(self) -> None: ...
    def reconfigure(self, profile: Profile) -> None: ...
    def warmup(self) -> None: ...


def fit_to_gpu(llm: Placeable, profile: Profile, installed: set[str] | None = None,
               log: Callable[[str], None] = print) -> Profile:
    """
    Verify placement after warm-up; step down until the model fits.

    Returns the profile that ended up running. Profiles that are not GPU plans
    (the CPU battery profile, or a manually chosen model) are returned as is.
    """
    plan = PLANS_BY_NAME.get(profile.name)
    if plan is None:
        return profile

    while True:
        placed = llm.placement()
        if placed is None:
            log("Placement: could not be read from Ollama; continuing without the check")
            return profile

        needed, on_gpu = placed
        share = on_gpu / needed if needed else 1.0
        if share >= FULLY_ON_GPU:
            log(f"Placement: 100% on the GPU ({needed:.1f} GB)")
            return profile

        log(f"Placement: only {share:.0%} on the GPU - part of the model spilled onto the CPU")
        lower = step_down(plan, installed)
        if lower is None:
            log("  no smaller configuration is available; continuing with the spill")
            return profile

        log(f"  stepping down: {plan.name} -> {lower.name}")
        # Unload first: Ollama keeps a model resident for a while after use,
        # and the smaller one would otherwise compete with it for the memory.
        llm.unload()
        profile = profile_from_plan(lower, reason=f"stepped down from {plan.name}, which spilled onto the CPU")
        llm.reconfigure(profile)
        llm.warmup()
        plan = lower
