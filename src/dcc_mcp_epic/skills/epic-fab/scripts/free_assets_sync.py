"""Plan or execute one bounded free-Fab sync through the typed worker."""

from __future__ import annotations

from typing import Optional, Sequence

from _common import exception_result, report_result
from dcc_mcp_core.skill import skill_entry


@skill_entry
def free_assets_sync(
    assets: Sequence[dict],
    allowed_root: str,
    mode: str,
    project_path: Optional[str] = None,
    free_only: bool = True,
    execute: bool = False,
    database_paths: Optional[Sequence[str]] = None,
    search_roots: Optional[Sequence[str]] = None,
    cache_roots: Optional[Sequence[str]] = None,
    **kwargs,
) -> dict:
    try:
        from dcc_mcp_epic.hooks import HOOK_PROTOCOL
        from dcc_mcp_epic.providers.fab.worker import FabWorker

        payload = {
            "assets": list(assets),
            "allowed_root": allowed_root,
            "mode": mode,
            "free_only": free_only,
            "dry_run": not execute,
        }
        for key, value in {
            "project_path": project_path,
            "database_paths": database_paths,
            "search_roots": search_roots,
            "cache_roots": cache_roots,
        }.items():
            if value is not None:
                payload[key] = value
        report = FabWorker().handle(
            {
                "protocol": HOOK_PROTOCOL,
                "operation": "fab.free_assets_sync.request",
                "payload": payload,
            }
        )
        message = (
            "Epic Fab free-asset sync executed"
            if execute
            else "Epic Fab free-asset sync dry-run completed"
        )
        return report_result(message, report)
    except Exception as exc:
        return exception_result("Epic Fab free-asset sync failed", exc)


def main(**kwargs) -> dict:
    return free_assets_sync(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
