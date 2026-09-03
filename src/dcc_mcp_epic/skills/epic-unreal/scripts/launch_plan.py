"""Create a read-only Unreal Editor launch plan."""

from __future__ import annotations

from typing import Optional

from _common import exception_result, report_result
from dcc_mcp_core.skill import skill_entry


@skill_entry
def launch_plan(
    target_version: str = "5.5",
    project_path: str = "",
    manifest_root: Optional[str] = None,
    **kwargs,
) -> dict:
    try:
        from dcc_mcp_epic.providers.epic_launcher.manifest import DEFAULT_MANIFEST_ROOT
        from dcc_mcp_epic.services import EpicService

        root = manifest_root or str(DEFAULT_MANIFEST_ROOT)
        report = EpicService().engine_launch_plan(target_version, project_path, root)
        return report_result("Unreal Editor launch plan created", report)
    except Exception as exc:
        return exception_result("Unreal Editor launch plan failed", exc)


def main(**kwargs) -> dict:
    return launch_plan(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
