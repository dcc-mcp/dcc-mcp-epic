"""Read and merge local Epic Fab index sources."""

from __future__ import annotations

from typing import Optional, Sequence

from _common import exception_result, report_result
from dcc_mcp_core.skill import skill_entry


@skill_entry
def library_sources(
    database_paths: Optional[Sequence[str]] = None,
    search_roots: Optional[Sequence[str]] = None,
    max_depth: int = 6,
    **kwargs,
) -> dict:
    try:
        from dcc_mcp_epic.providers.fab.service import FabService

        report = FabService().list_local_libraries(
            database_paths,
            search_roots=search_roots,
            max_depth=max_depth,
        )
        return report_result("Local Epic Fab library sources read", report)
    except Exception as exc:
        return exception_result("Local Epic Fab library source read failed", exc)


def main(**kwargs) -> dict:
    return library_sources(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
