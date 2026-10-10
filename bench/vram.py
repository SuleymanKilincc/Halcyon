"""
Measure how much GPU memory each component actually uses.

    python -m bench.vram                    # speech models + every pulled qwen3.5 size
    python -m bench.vram --llm qwen3.5:9b   # one language model only

The VRAM planner (core/vram.py) chooses models from these figures, so they
are measured rather than estimated:

* Speech-to-text: faster-whisper runs on CTranslate2, whose allocations are
  invisible to PyTorch's memory counters, so the device-wide usage reported by
  nvidia-smi is compared before and after loading each model.
* Language models: Ollama reports, for every loaded model, the total memory it
  needs (`size`) and how much of that actually landed on the GPU
  (`size_vram`). Loading the same model at several context lengths separates
  the fixed cost of the weights from the per-token cost of the KV cache.
"""

from __future__ import annotations

import argparse
import gc
import json
import subprocess
import sys
import time
import urllib.request

OLLAMA = "http://localhost:11434"
CONTEXTS = (4096, 8192, 16384, 32768)
GB = 1024 ** 3


def gpu_used_mib() -> int:
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, check=True,
    ).stdout
    return int(out.strip().splitlines()[0])


def settle(seconds: float = 2.0) -> int:
    time.sleep(seconds)
    return gpu_used_mib()


def _post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        OLLAMA + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as response:
        return json.loads(response.read() or b"{}")


def unload_all() -> None:
    with urllib.request.urlopen(OLLAMA + "/api/ps", timeout=30) as response:
        for model in json.load(response).get("models", []):
            _post("/api/generate", {"model": model["name"], "keep_alive": 0})
    time.sleep(2)


def ollama_footprint(model: str, num_ctx: int) -> tuple[float, float]:
    """Load `model` at `num_ctx`; return (needed GB, GB actually on the GPU)."""
    _post("/api/generate", {"model": model, "prompt": "", "keep_alive": "2m",
                            "options": {"num_ctx": num_ctx}})
    with urllib.request.urlopen(OLLAMA + "/api/ps", timeout=30) as response:
        for entry in json.load(response).get("models", []):
            if entry["name"] == model:
                return entry["size"] / GB, entry.get("size_vram", 0) / GB
    raise RuntimeError(f"{model} did not appear in /api/ps after loading")


def measure_whisper(names: list[str]) -> dict[str, float]:
    import numpy as np
    from faster_whisper import WhisperModel

    from voice.stt import load_cuda_runtime

    load_cuda_runtime()

    results = {}
    for name in names:
        before = settle()
        model = WhisperModel(name, device="cuda", compute_type="int8_float16")
        # Run once: buffers for inference are allocated on first use.
        model.transcribe(np.zeros(16000 * 5, dtype=np.float32), beam_size=5)
        after = settle()
        results[name] = (after - before) / 1024
        print(f"  whisper {name:<15} {results[name]:5.2f} GB")
        del model
        gc.collect()
        settle(3)
    return results


def installed_qwen() -> list[str]:
    with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=30) as response:
        names = [m["name"] for m in json.load(response).get("models", [])]
    return sorted((n for n in names if n.startswith("qwen3.5:")),
                  key=lambda n: float(n.split(":")[1].rstrip("b")))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--llm", action="append", help="language model(s) to measure")
    parser.add_argument("--whisper", nargs="*", default=["base", "small", "large-v3-turbo"])
    parser.add_argument("--json", help="also write the results to this file")
    args = parser.parse_args()

    unload_all()
    baseline = settle()
    print(f"GPU memory in use with nothing loaded: {baseline / 1024:.2f} GB\n")

    print("Speech-to-text (int8_float16, after one inference):")
    whisper = measure_whisper(args.whisper) if args.whisper else {}

    print("\nLanguage models (needed / on GPU), by context length:")
    llms: dict[str, dict[int, tuple[float, float]]] = {}
    for model in args.llm or installed_qwen():
        llms[model] = {}
        row = []
        for ctx in CONTEXTS:
            needed, on_gpu = ollama_footprint(model, ctx)
            llms[model][ctx] = (needed, on_gpu)
            mark = "" if on_gpu >= needed - 0.01 else " (spilled)"
            row.append(f"{ctx // 1024:>2}k {needed:5.2f}/{on_gpu:5.2f}{mark}")
        print(f"  {model:<12} " + " | ".join(row))
        unload_all()

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump({"baseline_gb": baseline / 1024, "whisper_gb": whisper,
                       "llm_gb": {m: {str(c): v for c, v in d.items()} for m, d in llms.items()}},
                      handle, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
