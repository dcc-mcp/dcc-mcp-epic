from __future__ import annotations

import os
from typing import Any, Dict, Optional

import psutil

from ...models import LauncherBinding


def _window_owner(hwnd: int) -> Optional[int]:
    if os.name != "nt":
        return None
    import ctypes

    user32 = ctypes.windll.user32
    if not user32.IsWindow(hwnd):
        return None
    owner = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
    return int(owner.value)


def bind_launcher(binding: LauncherBinding) -> "LauncherRuntime":
    if binding.pid <= 0 or binding.hwnd <= 0:
        raise ValueError("pid and hwnd must be positive")
    try:
        process = psutil.Process(binding.pid)
        if not process.is_running():
            raise ValueError(f"launcher process is not running: {binding.pid}")
    except psutil.Error as exc:
        raise ValueError(f"cannot inspect launcher process {binding.pid}: {exc}") from exc

    owner = _window_owner(binding.hwnd)
    if owner is not None and owner != binding.pid:
        raise ValueError(f"hwnd {binding.hwnd} belongs to pid {owner}, not {binding.pid}")
    return LauncherRuntime(binding=binding)


class LauncherRuntime:
    def __init__(self, binding: LauncherBinding) -> None:
        self.binding = binding

    def status(self) -> Dict[str, Any]:
        process = psutil.Process(self.binding.pid)
        executable = None
        try:
            executable = process.exe()
        except psutil.Error:
            pass
        return {
            "pid": self.binding.pid,
            "hwnd": self.binding.hwnd,
            "version": self.binding.version,
            "expected_executable": str(self.binding.executable),
            "actual_executable": executable,
            "running": process.is_running(),
            "window_identity_checked": _window_owner(self.binding.hwnd) is not None,
        }
