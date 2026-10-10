"""
Tests for placement verification (core/fit.py).

A fake model stands in for Ollama and reports a scripted placement, so the
step-down logic can be exercised without a GPU or a server.
"""

from core.fit import fit_to_gpu
from core.profiles import BATTERY, PROFILES


class FakeLLM:
    def __init__(self, placements):
        self.placements = list(placements)  # one (needed, on_gpu) per check
        self.calls = []
        self.model = None

    def placement(self):
        self.calls.append("placement")
        return self.placements.pop(0)

    def unload(self):
        self.calls.append(f"unload {self.model}")

    def reconfigure(self, profile):
        self.model = profile.llm_model
        self.calls.append(f"reconfigure {profile.name}")

    def warmup(self):
        self.calls.append("warmup")


def quiet(_message):
    pass


def test_a_model_fully_on_the_gpu_is_kept():
    llm = FakeLLM([(5.24, 5.24)])
    profile = fit_to_gpu(llm, PROFILES["gpu-9b-8k"], log=quiet)
    assert profile.name == "gpu-9b-8k"
    assert llm.calls == ["placement"]


def test_a_spilled_model_is_unloaded_and_the_next_rung_tried():
    # Measured case: 9B at 16k needed 6.10 GB and only 5.12 landed on the GPU.
    llm = FakeLLM([(6.10, 5.12), (5.24, 5.24)])
    llm.model = "qwen3.5:9b"
    profile = fit_to_gpu(llm, PROFILES["gpu-9b-16k"], log=quiet)
    assert profile.name == "gpu-9b-8k"
    assert llm.calls == [
        "placement",
        "unload qwen3.5:9b",          # before loading the smaller one
        "reconfigure gpu-9b-8k",
        "warmup",
        "placement",
    ]
    assert "spilled" in profile.reason


def test_keeps_stepping_down_until_it_fits():
    llm = FakeLLM([(6.74, 5.1), (6.10, 5.1), (5.24, 5.24)])
    profile = fit_to_gpu(llm, PROFILES["gpu-9b-32k"], log=quiet)
    assert profile.name == "gpu-9b-8k"


def test_only_installed_models_are_stepped_down_to():
    llm = FakeLLM([(5.24, 3.0), (2.30, 2.30)])
    profile = fit_to_gpu(llm, PROFILES["gpu-9b-8k"], installed={"qwen3.5:2b"}, log=quiet)
    assert profile.llm_model == "qwen3.5:2b"


def test_bottom_rung_that_spills_is_kept_with_a_message():
    messages = []
    llm = FakeLLM([(2.19, 1.0)])
    profile = fit_to_gpu(llm, PROFILES["gpu-2b-4k-base"], log=messages.append)
    assert profile.name == "gpu-2b-4k-base"
    assert any("no smaller configuration" in m for m in messages)


def test_unreadable_placement_does_not_block_startup():
    llm = FakeLLM([None])
    assert fit_to_gpu(llm, PROFILES["gpu-9b-8k"], log=quiet).name == "gpu-9b-8k"


def test_cpu_profile_is_not_checked_at_all():
    # On the battery profile everything is on the CPU by design; a placement
    # check would read 0% on the GPU and wrongly try to "fix" it.
    llm = FakeLLM([])
    assert fit_to_gpu(llm, BATTERY, log=quiet) is BATTERY
    assert llm.calls == []
