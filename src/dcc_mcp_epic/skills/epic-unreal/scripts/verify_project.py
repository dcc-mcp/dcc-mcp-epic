"""Read-only UE project verification."""

from __future__ import annotations

from _common import exception_result, report_result
from dcc_mcp_core.skill import skill_entry


@skill_entry
def verify_project(project_path: str, expected_engine: str = "5.5", **kwargs) -> dict:
    try:
        from dcc_mcp_epic.providers.unreal.project import verify_project as run_verify

        return report_result(
            "Unreal project verification completed",
            run_verify(project_path, expected_engine),
        )
    except Exception as exc:
        return exception_result("Unreal project verification failed", exc)


def main(**kwargs) -> dict:
    return verify_project(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
