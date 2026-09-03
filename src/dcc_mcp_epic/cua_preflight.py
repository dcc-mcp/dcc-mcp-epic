"""Read-only preflight for the project-owned dcc-cua route.

The preflight deliberately stops before any input operation.  It verifies the
runtime, host session, visual route, and exact PID/HWND binding so callers can
decide whether a UI fallback is safe without guessing or retrying blindly.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple, Union

DCC_CUA_COMMAND_ENV = "DCC_MCP_EPIC_CUA_COMMAND"
DEFAULT_TIMEOUT_SECONDS = 10


def _error(code: str, message: str, **details: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {"code": code, "message": message}
    result.update(details)
    return result


def _resolve_command(
    cua_command: Optional[Sequence[str]],
) -> Tuple[Optional[Tuple[str, ...]], Optional[Dict[str, Any]]]:
    """Resolve only an explicit executable or the official local dcc-cua path."""

    command: Optional[Sequence[str]] = cua_command
    if command is None:
        raw = os.environ.get(DCC_CUA_COMMAND_ENV, "").strip()
        if raw:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                return None, _error(
                    "invalid_command_configuration",
                    f"{DCC_CUA_COMMAND_ENV} must be a JSON array",
                    reason=str(exc),
                )
            command = parsed
    if command is not None:
        if (
            isinstance(command, (str, bytes))
            or not command
            or not all(isinstance(item, str) and item.strip() for item in command)
        ):
            return None, _error(
                "invalid_command_configuration",
                "dcc-cua command must be a non-empty sequence of strings",
            )
        executable = Path(str(command[0])).expanduser()
        if not executable.is_absolute() or not executable.is_file():
            return None, _error(
                "command_not_found",
                "dcc-cua executable must be an existing absolute file",
                executable=str(executable),
            )
        return tuple(str(item) for item in command), None

    candidates = []
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "dcc-mcp" / "bin" / "dcc-cua.exe")
    for candidate in candidates:
        if candidate.is_file():
            return (str(candidate.resolve()),), None
    return None, _error(
        "command_not_found",
        "official dcc-cua executable was not found",
        searched=[str(item) for item in candidates],
    )


def _run(
    command: Sequence[str],
    arguments: Sequence[str],
    timeout_seconds: int,
    *,
    allow_nonzero: bool = False,
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    argv = [*command, *arguments]
    try:
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, _error(
            "command_failed", "dcc-cua command could not be started", reason=str(exc)
        )
    output = (completed.stdout or completed.stderr or "").strip()
    if completed.returncode != 0 and not allow_nonzero:
        return None, _error(
            "nonzero_exit",
            "dcc-cua command returned a non-zero exit code",
            returncode=completed.returncode,
            output=output[-4096:],
        )
    return output, None


def _run_json(
    command: Sequence[str],
    arguments: Sequence[str],
    timeout_seconds: int,
    *,
    allow_nonzero: bool = False,
) -> Tuple[Optional[Any], Optional[Dict[str, Any]]]:
    output, failure = _run(
        command,
        arguments,
        timeout_seconds,
        allow_nonzero=allow_nonzero,
    )
    if failure:
        return None, failure
    try:
        return json.loads(output or ""), None
    except (TypeError, ValueError) as exc:
        return None, _error("invalid_json", "dcc-cua returned invalid JSON", reason=str(exc))


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def preflight_launcher(
    pid: int,
    hwnd: int,
    executable: Union[str, Path],
    *,
    cua_command: Optional[Sequence[str]] = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    """Return a typed, no-side-effect readiness report for one Launcher window.

    The command sequence is limited to ``--version``, ``ping``, ``doctor`` and
    exact-window ``list``.  It never sends mouse, keyboard, text, URL, or shell
    actions.
    """

    try:
        target_pid = _positive_int(pid, "pid")
        target_hwnd = _positive_int(hwnd, "hwnd")
    except ValueError as exc:
        return {
            "provider": "dcc-cua",
            "status": "unavailable",
            "ready": False,
            "action_ready": False,
            "error": _error("invalid_target", str(exc)),
            "side_effects_performed": False,
        }
    target_executable = Path(executable).expanduser().resolve()
    target = {
        "pid": target_pid,
        "hwnd": target_hwnd,
        "executable": str(target_executable),
    }
    report: Dict[str, Any] = {
        "provider": "dcc-cua",
        "status": "unavailable",
        "ready": False,
        "action_ready": False,
        "target": target,
        "side_effects_performed": False,
    }
    try:
        timeout = max(1, min(int(timeout_seconds), 60))
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT_SECONDS
    command, failure = _resolve_command(cua_command)
    if failure or command is None:
        report["error"] = failure or _error("command_not_found", "dcc-cua command is unavailable")
        return report
    report["command"] = list(command)

    version_output, failure = _run(command, ["--version"], timeout)
    if failure:
        report["error"] = failure
        return report
    report["runtime"] = (version_output or "").splitlines()[0].strip() or None

    ping, failure = _run_json(command, ["ping"], timeout)
    if failure:
        report["error"] = failure
        return report
    report["ping"] = ping

    # ``doctor`` uses exit code 1 for a degraded-but-valid diagnostic report;
    # the JSON body is the authoritative result and must still be consumed.
    doctor, failure = _run_json(
        command,
        ["doctor", "--route", "visual"],
        timeout,
        allow_nonzero=True,
    )
    if failure:
        report["error"] = failure
        return report
    if not isinstance(doctor, dict):
        report["error"] = _error(
            "invalid_doctor_response", "dcc-cua doctor response must be an object"
        )
        return report
    report["doctor"] = doctor
    report["routes"] = doctor.get("routes", {})
    checks = doctor.get("checks", {})
    nested_desktop = checks.get("interactive_desktop", {}) if isinstance(checks, dict) else {}
    report["interactive_desktop"] = doctor.get("interactive_desktop", nested_desktop)

    windows, failure = _run_json(
        command,
        ["list", "--pid", str(target_pid), "--window-id", str(target_hwnd)],
        timeout,
    )
    if failure:
        report["error"] = failure
        return report
    if not isinstance(windows, list):
        report["error"] = _error(
            "invalid_window_response", "dcc-cua list response must be an array"
        )
        return report
    window = next(
        (
            item
            for item in windows
            if isinstance(item, dict)
            and item.get("pid") == target_pid
            and item.get("window_id") == target_hwnd
        ),
        None,
    )
    report["window"] = window
    if window is None:
        report["status"] = "blocked"
        report["error"] = _error(
            "exact_window_not_found",
            "dcc-cua did not return the exact bound PID/HWND",
        )
        if report["interactive_desktop"].get("code") == "interactive_session_not_active":
            report["next_action"] = "reconnect the bound Windows interactive session"
        else:
            report["next_action"] = "rebind the current Launcher PID/HWND"
        return report

    expected_app = target_executable.name.casefold()
    actual_app = str(window.get("app_name") or "").casefold()
    if actual_app and actual_app != expected_app:
        report["status"] = "blocked"
        report["error"] = _error(
            "exact_window_executable_mismatch",
            "exact window belongs to a different executable",
            expected=expected_app,
            actual=actual_app,
        )
        report["next_action"] = "rebind the Launcher executable"
        return report

    desktop = report["interactive_desktop"]
    visual_route = report["routes"].get("visual", {}) if isinstance(report["routes"], dict) else {}
    visual_ready = bool(doctor.get("ready")) and bool(visual_route.get("ready", True))
    visible = bool(window.get("is_on_screen", True)) and not bool(window.get("minimized", False))
    report["ready"] = visual_ready and visible
    report["action_ready"] = report["ready"] and bool(desktop.get("input_ready"))
    if report["ready"]:
        report["status"] = "ready"
    else:
        report["status"] = "blocked"
        if desktop.get("code") == "interactive_session_not_active":
            report["next_action"] = "reconnect the bound Windows interactive session"
        elif not visible:
            report["next_action"] = "restore the exact Launcher window on screen"
        else:
            report["next_action"] = "repair the dcc-cua visual route and re-run preflight"
    return report
