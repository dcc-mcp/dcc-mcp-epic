"""Read installed Unreal Engine manifests."""

from __future__ import annotations

from typing import Optional

from _common import exception_result, report_result
from dcc_mcp_core.skill import skill_entry


@skill_entry
def list_installed_engines(manifest_root: Optional[str] = None, **kwargs) -> dict:
    try:
        from dcc_mcp_epic.providers.epic_launcher.manifest import DEFAULT_MANIFEST_ROOT
        from dcc_mcp_epic.services import EpicService

        root = manifest_root or str(DEFAULT_MANIFEST_ROOT)
        return report_result(
            "Installed Unreal Engine inventory read",
            EpicService().list_engines(root),
        )
    except Exception as exc:
        return exception_result("Installed Unreal Engine inventory failed", exc)


def main(**kwargs) -> dict:
    return list_installed_engines(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
