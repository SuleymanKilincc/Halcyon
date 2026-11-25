"""
Model packs: which model "deep mode" runs on, by what the machine can carry.

Deep mode (core/modes.py) is the mode for heavy work: a big coding job, a long
story with a world to keep track of. It needs a larger model than everyday talk,
and a larger model needs more memory, so there is one pack per size class. A pack
is nothing but a model name with the requirements and the evidence behind them.

Only what has been measured is called measured. A pack's `tested` says on which
machine it ran and what came out; the requirements below that are estimates, and
the descriptions say so. When more machines have been tried, change the numbers
here (and in docs/MODES.md); nothing else needs to know.

This module is pure: it reads a Hardware object and a set of installed model names.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from core.hardware import Hardware


@dataclass(frozen=True)
class Pack:
    key: str
    name: str                     # what the user is offered ("Standard")
    deep_model: str               # the Ollama model deep mode runs on
    download_gb: float            # disk, and the download
    min_total_gb: float           # VRAM + RAM together: the model, its context, and the rest of Halcyon
    min_vram_gb: float            # floor: the card must exist and hold the speech model and some layers
    min_ram_gb: float             # floor: the system and Halcyon's own models need room whatever the card is
    load_seconds: tuple[int, int]  # first load after another model; disk-cache dependent
    tested: str                   # the measured machine and result, in words
    summary: str                  # one line: what it is good for


# Best first: the first pack a machine satisfies is the one recommended to it.
PACKS: tuple[Pack, ...] = (
    Pack(
        key="standard",
        name="Standard",
        deep_model="gemma4:26b-a4b",
        download_gb=18,
        min_total_gb=32,
        min_vram_gb=4,
        min_ram_gb=8,
        load_seconds=(30, 120),
        tested=("RTX 4060 Laptop 8 GB + 32 GB RAM: about 40 tokens/s with part of the model on the CPU; "
                "hard code set 6/8, film and game knowledge 6/6 (Turkish and English), the world rules "
                "held for a five-turn scenario"),
        summary="Large mixture-of-experts model (about 4B active parameters): the best measured answer "
                "for code, facts and stories",
    ),
    Pack(
        key="light",
        name="Light",
        deep_model="gemma4:e4b",
        download_gb=9.6,
        min_total_gb=16,
        min_vram_gb=4,
        min_ram_gb=8,
        load_seconds=(10, 30),
        tested="RTX 4060 Laptop 8 GB + 32 GB RAM (see docs/MODES.md for the numbers)",
        summary="Small and fast; fits on a modest card",
    ),
)

# What the development machine is, so a requirement can be called "measured" or "estimated".
TESTED_VRAM_GB = 8.0
TESTED_RAM_GB = 32.0

# A card sold as "8 GB" reports about 7.9 and a "16 GB" laptop about 15.6 of RAM, so a
# requirement is met a little under its nominal size.
_SLACK_TOTAL_GB = 1.5
_SLACK_FLOOR_GB = 0.5


def usable_vram_gb(hardware: Hardware) -> float:
    """
    The card memory Halcyon can actually use: what is free at start-up (memory an idle Ollama
    model holds counts as free, see core/hardware.py), or the total when that cannot be read.
    A card that other programs fill is not an 8 GB card for this purpose.
    """
    return hardware.vram_free_gb if hardware.vram_free_gb is not None else hardware.vram_gb


def fits(pack: Pack, hardware: Hardware | None) -> bool:
    """Does the machine meet the pack's requirements? No GPU: no pack (CPU-only is far too slow)."""
    if hardware is None:           # unknown machine: assume the one this was measured on
        return True
    if not hardware.cuda:
        return False
    vram = usable_vram_gb(hardware)
    return (vram >= pack.min_vram_gb - _SLACK_FLOOR_GB
            and hardware.ram_gb >= pack.min_ram_gb - _SLACK_FLOOR_GB
            and vram + hardware.ram_gb >= pack.min_total_gb - _SLACK_TOTAL_GB)


def candidates(hardware: Hardware | None) -> list[Pack]:
    return [pack for pack in PACKS if fits(pack, hardware)]


def choose_pack(hardware: Hardware | None, installed: set[str] | None = None) -> Pack | None:
    """
    The pack deep mode should use, or None when this machine carries none of them.

    A pack that is already installed wins over a better one that is not, so a machine
    that can carry Standard but only has Light keeps working; with nothing installed
    the best pack that fits is the recommendation.
    """
    options = candidates(hardware)
    if not options:
        return None
    if installed is not None:
        for pack in options:
            if pack.deep_model in installed:
                return pack
    return options[0]


def verdict(pack: Pack, hardware: Hardware | None) -> str:
    """'measured', 'estimated' or 'too small' for this machine, as a short word."""
    if not fits(pack, hardware):
        return "too small"
    if hardware is None:
        return "measured"
    # "Measured" only for a machine like the one the pack was run on; anything else that fits is a
    # well-founded guess (more of the model on the card should be faster, less of it slower).
    same_class = (abs(hardware.vram_gb - TESTED_VRAM_GB) <= 1.0 and abs(hardware.ram_gb - TESTED_RAM_GB) <= 4.0)
    return "measured" if same_class else "estimated"


def describe(hardware: Hardware | None, installed: set[str] | None = None) -> str:
    """The packs, for `--info`: what each needs, whether this machine has it, whether it is installed."""
    lines = ["Deep mode packs (heavy coding, long stories):"]
    chosen = choose_pack(hardware, installed)
    for pack in PACKS:
        state = verdict(pack, hardware)
        have = ""
        if installed is not None:
            have = ", installed" if pack.deep_model in installed else ", not installed"
        mark = "->" if chosen is not None and pack.key == chosen.key else "  "
        lines.append(f" {mark} {pack.name}: {pack.deep_model}, {pack.download_gb:g} GB download, "
                     f"needs about {pack.min_total_gb:g} GB of VRAM + RAM together "
                     f"(at least {pack.min_vram_gb:g} GB VRAM and {pack.min_ram_gb:g} GB RAM) "
                     f"[{state}{have}]")
        lines.append(f"      {pack.summary}")
    if chosen is None:
        lines.append("    No pack fits this machine: deep mode is off and everything runs in general mode.")
    return "\n".join(lines)


def env_model(env: Mapping[str, str]) -> str | None:
    """A model the user named themselves (HALCYON_DEEP_MODEL); it is used whatever the hardware says."""
    return env.get("HALCYON_DEEP_MODEL") or None
