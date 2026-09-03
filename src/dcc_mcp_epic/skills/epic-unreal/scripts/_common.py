"""Shared result shaping for Epic Unreal skill scripts."""

from __future__ import annotations

from typing import Any, Dict

from dcc_mcp_core.skill import skill_error, skill_success, skill_warning


def as_report(value: Any) -> Dict[str, Any]:
    if hasattr(value, "as_dict"):
        value = value.as_dict()
    return value if isinstance(value, dict) else {"value": value}


def report_result(message: str, value: Any) -> dict:
    report = as_report(value)
    state = str(report.get("state") or report.get("status") or "").casefold()
    failed = report.get("ok") is False or state in {"blocked", "unavailable", "human_required"}
    if failed:
        return skill_warning(
            message,
            warning=str(
                report.get("message")
                or report.get("reason")
                or report.get("error")
                or "typed check did not pass"
            ),
            prompt=str(
                report.get("next_action")
                or report.get("details", {}).get("next_action")
                or ""
            ),
            report=report,
        )
    return skill_success(
        message,
        verified=True,
        postcondition={"method": "typed_adapter_readback", "state": state or "reported"},
        report=report,
    )


def exception_result(message: str, exc: Exception) -> dict:
    return skill_error(
        message,
        error=str(exc),
        possible_solutions=[
            "check the Epic adapter installation",
            "retry after correcting the supplied path",
        ],
    )
