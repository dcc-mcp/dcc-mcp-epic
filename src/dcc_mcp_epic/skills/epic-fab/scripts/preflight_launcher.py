"""Read-only exact-window dcc-cua preflight for Epic Games Launcher."""

from __future__ import annotations

from typing import Optional

from _common import exception_result, report_result
from dcc_mcp_core.skill import skill_entry


@skill_entry
def preflight_launcher(
    pid: int,
    hwnd: int,
    executable: str,
    cua_path: Optional[str] = None,
    timeout_seconds: int = 10,
    **kwargs,
) -> dict:
    try:
        from dcc_mcp_epic.cua_preflight import preflight_launcher as run_preflight

        command = [cua_path] if cua_path else None
        report = run_preflight(
            pid,
            hwnd,
            executable,
            cua_command=command,
            timeout_seconds=timeout_seconds,
        )
        return report_result("Epic Launcher dcc-cua preflight completed", report)
    except Exception as exc:
        return exception_result("Epic Launcher dcc-cua preflight failed", exc)


def main(**kwargs) -> dict:
    return preflight_launcher(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
