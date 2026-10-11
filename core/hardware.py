"""
Hardware detection.

Answers one question the rest of the system needs before it picks any model:
what can this machine actually do *right now*? On a laptop that changes during
a single day — a discrete GPU can be switched off between two runs of the same
program — so the answer is detected at startup, never assumed or cached to disk.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field


@dataclass
class Hardware:
    cuda: bool = False
    gpu_name: str | None = None
    vram_gb: float = 0.0
    # Free VRAM at startup, read from nvidia-smi. The desktop and other
    # programs already occupy part of the card, so planning against the
    # total would overcommit. None when it cannot be read.
    vram_free_gb: float | None = None

    # A discrete GPU that Windows knows about but is not currently attached to
    # the PCI bus. On ASUS laptops this is the normal state in G-Helper's
    # "Eco" / iGPU-only mode, and it is worth distinguishing from "no GPU at
    # all": the fix is a setting and a reboot, not new hardware.
    dgpu_disconnected: bool = False
    dgpu_name: str | None = None

    on_battery: bool = False
    battery_percent: float | None = None

    cpu_physical: int = 0
    cpu_logical: int = 0
    ram_gb: float = 0.0

    notes: list[str] = field(default_factory=list)

    @property
    def accelerated(self) -> bool:
        return self.cuda

    def summary(self) -> str:
        lines = []
        if self.cuda:
            free = f", {self.vram_free_gb:.1f} GB free" if self.vram_free_gb is not None else ""
            lines.append(f"GPU : {self.gpu_name} ({self.vram_gb:.1f} GB VRAM{free}), CUDA available")
        elif self.dgpu_disconnected:
            lines.append(f"GPU : {self.dgpu_name} is installed but NOT CONNECTED (Code 45)")
            lines.append("      Switch the GPU mode to Standard (e.g. in G-Helper or Armoury Crate) and restart")
        else:
            lines.append("GPU : no CUDA device")
        power = "battery" if self.on_battery else "plugged in"
        if self.battery_percent is not None:
            power += f" {self.battery_percent:.0f}%"
        lines.append(f"CPU : {self.cpu_physical} cores / {self.cpu_logical} threads")
        lines.append(f"RAM : {self.ram_gb:.0f} GB   |   Power: {power}")
        return "\n".join(lines)


def _detect_cuda() -> tuple[bool, str | None, float]:
    try:
        import torch
    except Exception:  # noqa: BLE001
        return False, None, 0.0
    if not torch.cuda.is_available():
        return False, None, 0.0
    props = torch.cuda.get_device_properties(0)
    return True, torch.cuda.get_device_name(0), props.total_memory / 1024**3


def _detect_disconnected_dgpu(timeout: float = 8.0) -> tuple[bool, str | None]:
    """
    Look for a display adapter Windows has a driver for but cannot see.

    Only ``Get-PnpDevice`` reports these; WMI's ``Win32_VideoController`` and
    ``Win32_PnPEntity`` list present devices only, which is exactly why an
    absent-but-installed GPU looks like no GPU at all from Python.
    """
    if sys.platform != "win32":
        return False, None
    script = (
        "Get-PnpDevice -Class Display -ErrorAction SilentlyContinue | "
        "Where-Object { $_.Present -eq $false } | "
        "Select-Object -First 1 -Property FriendlyName | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=timeout,
        )
    except Exception:  # noqa: BLE001 - detection must never break startup
        return False, None

    payload = (result.stdout or "").strip()
    if not payload:
        return False, None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return False, None
    if isinstance(data, list):
        data = data[0] if data else None
    if not isinstance(data, dict):
        return False, None
    name = data.get("FriendlyName")
    return bool(name), name


def detect(*, probe_dgpu: bool = True) -> Hardware:
    hw = Hardware()

    hw.cuda, hw.gpu_name, hw.vram_gb = _detect_cuda()
    if hw.cuda:
        from core.vram import ollama_resident_gib, query_free_vram_gib

        reading = query_free_vram_gib()
        if reading is not None:
            # Memory an idle Ollama model still holds is available to us.
            free, total = reading
            hw.vram_free_gb = min(total, free + ollama_resident_gib())

    # Only worth the PowerShell round trip when there is no working GPU: if
    # CUDA already answers, we do not care what else is installed.
    if not hw.cuda and probe_dgpu:
        hw.dgpu_disconnected, hw.dgpu_name = _detect_disconnected_dgpu()

    try:
        import psutil

        hw.cpu_physical = psutil.cpu_count(logical=False) or 0
        hw.cpu_logical = psutil.cpu_count(logical=True) or 0
        hw.ram_gb = psutil.virtual_memory().total / 1024**3
        battery = psutil.sensors_battery()
        if battery is not None:
            hw.on_battery = not battery.power_plugged
            hw.battery_percent = float(battery.percent)
    except Exception as exc:  # noqa: BLE001
        hw.notes.append(f"could not read hardware details via psutil: {exc}")
        hw.cpu_logical = os.cpu_count() or 4
        hw.cpu_physical = max(1, hw.cpu_logical // 2)

    return hw


if __name__ == "__main__":
    print(detect().summary())
