"""Search the local merged Epic Fab library without contacting Fab."""

from __future__ import annotations

from typing import Optional, Sequence

from _common import exception_result, report_result
from dcc_mcp_core.skill import skill_entry


@skill_entry
def search_library(
    query: str = "",
    category: str = "",
    formats: Optional[Sequence[str]] = None,
    owned_only: bool = False,
    downloaded_only: bool = False,
    database_paths: Optional[Sequence[str]] = None,
    search_roots: Optional[Sequence[str]] = None,
    max_depth: int = 6,
    **kwargs,
) -> dict:
    try:
        from dcc_mcp_epic.providers.fab.service import FabService

        report = FabService().search_local_library(
            query,
            database_paths,
            search_roots=search_roots,
            category=category,
            formats=formats,
            owned_only=owned_only,
            downloaded_only=downloaded_only,
            max_depth=max_depth,
        )
        return report_result("Local Epic Fab library search completed", report)
    except Exception as exc:
        return exception_result("Local Epic Fab library search failed", exc)


def main(**kwargs) -> dict:
    return search_library(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
