"""
Tests for the model packs (core/packs.py): which machine gets which deep-mode model.

The numbers in PACKS are partly measured and partly estimated; these tests pin the
rules around them (best pack first, an installed pack wins, no GPU means no pack),
not the numbers, so changing a requirement after testing another machine is one edit
in core/packs.py.
"""

from core.hardware import Hardware
from core.packs import PACKS, choose_pack, describe, fits, verdict

STANDARD, LIGHT = PACKS[0], PACKS[1]

DEV_MACHINE = Hardware(cuda=True, vram_gb=7.99, ram_gb=31.6)   # the RTX 4060 Laptop the packs were measured on
MODEST = Hardware(cuda=True, vram_gb=6.0, ram_gb=16.0)
TINY = Hardware(cuda=True, vram_gb=4.0, ram_gb=8.0)
BIG = Hardware(cuda=True, vram_gb=24.0, ram_gb=64.0)
NO_GPU = Hardware(cuda=False, vram_gb=0.0, ram_gb=64.0)
EVEN_SPLIT = Hardware(cuda=True, vram_gb=15.6, ram_gb=15.6)    # a "16 GB + 16 GB" machine as the system reports it
BIG_CARD_LITTLE_RAM = Hardware(cuda=True, vram_gb=24.0, ram_gb=8.0)
SMALL_CARD_BIG_RAM = Hardware(cuda=True, vram_gb=4.0, ram_gb=32.0)
BARELY_A_CARD = Hardware(cuda=True, vram_gb=2.0, ram_gb=64.0)


def test_the_machine_the_packs_were_measured_on_gets_the_standard_pack():
    assert choose_pack(DEV_MACHINE).key == "standard"


def test_a_modest_machine_gets_the_light_pack():
    assert choose_pack(MODEST).key == "light"


def test_a_machine_that_is_too_small_gets_nothing_rather_than_something_too_slow():
    assert choose_pack(TINY) is None
    assert choose_pack(NO_GPU) is None


def test_the_requirement_is_the_total_not_one_kind_of_memory():
    """16 GB of VRAM + 16 GB of RAM carries the pack that 8 + 24 does: the model is split between them."""
    for machine in (DEV_MACHINE, EVEN_SPLIT, BIG_CARD_LITTLE_RAM, SMALL_CARD_BIG_RAM):
        assert choose_pack(machine).key == "standard", machine


def test_but_each_kind_has_a_floor_so_a_huge_total_in_one_kind_is_not_enough():
    assert choose_pack(BARELY_A_CARD) is None                 # 66 GB in total, but no card to speak of
    assert choose_pack(Hardware(cuda=True, vram_gb=24.0, ram_gb=4.0)) is None   # no room for the system


def test_a_bigger_machine_still_gets_the_best_pack_there_is():
    assert choose_pack(BIG).key == "standard"


def test_unknown_hardware_is_taken_to_be_the_measured_machine():
    assert choose_pack(None).key == "standard"


def test_a_pack_that_is_installed_wins_over_a_better_one_that_is_not():
    assert choose_pack(DEV_MACHINE, {LIGHT.deep_model}).key == "light"
    assert choose_pack(DEV_MACHINE, {STANDARD.deep_model, LIGHT.deep_model}).key == "standard"
    assert choose_pack(DEV_MACHINE, set()).key == "standard"           # nothing installed: recommend the best


def test_an_installed_pack_the_machine_cannot_carry_is_not_chosen():
    assert choose_pack(MODEST, {STANDARD.deep_model}).key == "light"


def test_the_card_sold_as_8_gb_is_not_turned_away_for_reporting_7_9():
    assert fits(STANDARD, Hardware(cuda=True, vram_gb=7.9, ram_gb=32))


def test_the_verdict_separates_measured_from_estimated():
    assert verdict(STANDARD, DEV_MACHINE) == "measured"
    assert verdict(STANDARD, BIG) == "estimated"         # fits, but nothing was ever run on it
    assert verdict(STANDARD, EVEN_SPLIT) == "estimated"
    assert verdict(STANDARD, TINY) == "too small"


def test_every_pack_says_what_it_was_measured_on_and_has_a_download_size():
    for pack in PACKS:
        assert pack.tested and pack.download_gb > 0 and pack.deep_model
    assert [p.min_total_gb for p in PACKS] == sorted((p.min_total_gb for p in PACKS), reverse=True)  # best first


def test_the_description_marks_the_recommendation_and_what_is_installed():
    text = describe(DEV_MACHINE, {STANDARD.deep_model})
    assert f"-> Standard: {STANDARD.deep_model}" in text
    assert "of VRAM + RAM together" in text
    assert "[measured, installed]" in text and "[measured, not installed]" in text
    assert "No pack fits" in describe(TINY, set())


def test_a_card_that_other_programs_fill_is_judged_by_what_is_free():
    busy = Hardware(cuda=True, vram_gb=8.0, vram_free_gb=2.0, ram_gb=32.0)
    assert choose_pack(busy) is None                         # 2 GB free is below every floor
    quiet = Hardware(cuda=True, vram_gb=8.0, vram_free_gb=6.8, ram_gb=31.6)
    assert choose_pack(quiet).key == "standard"              # the development machine with a music player open
