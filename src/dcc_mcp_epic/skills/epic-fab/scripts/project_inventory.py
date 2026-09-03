"""Read Fab provenance manifests and hashes in a UE project."""

from __future__ import annotations

from _common import exception_result, report_result
from dcc_mcp_core.skill import skill_entry


@skill_entry
def project_inventory(
    project_path: str,
    allowed_root: str,
    destination_subdir: str = "Fab",
    **kwargs,
) -> dict:
    try:
        from dcc_mcp_epic.providers.fab.service import FabService

        report = FabService().project_import_inventory(
            project_path,
            allowed_root,
            destination_subdir=destination_subdir,
        )
        return report_result("Epic Fab project inventory completed", report)
    except Exception as exc:
        return exception_result("Epic Fab project inventory failed", exc)


def main(**kwargs) -> dict:
    return project_inventory(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
