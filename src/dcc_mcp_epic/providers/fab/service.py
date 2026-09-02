from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Union

from ...models import CapabilityState, OperationResult
from ...policy import require_free_asset, resolve_allowed_project

DEFAULT_FAB_LIBRARY_DB = (
    Path(os.environ.get("ProgramData", r"C:\ProgramData"))
    / "Epic"
    / "EpicGamesLauncher"
    / "VaultCache"
    / "FabLibrary"
    / "listings_v1.db"
)


class FabService:
    """Fab boundary. It never emulates marketplace clicks or stores credentials."""

    def capabilities(self) -> Dict[str, Any]:
        return {
            "search": CapabilityState.UNAVAILABLE.value,
            "library": CapabilityState.READ_ONLY.value,
            "download": CapabilityState.UNAVAILABLE.value,
            "export": CapabilityState.UNAVAILABLE.value,
            "reason": "No stable public local Fab automation API has been verified",
            "human_boundary": ["login", "captcha", "2fa", "license_agreement", "purchase"],
        }

    def list_local_library(
        self, database_path: Union[str, Path] = DEFAULT_FAB_LIBRARY_DB
    ) -> Dict[str, Any]:
        """Read Epic's local Fab library index without changing it."""

        path = Path(database_path).expanduser().resolve()
        if not path.exists():
            return {"db_path": str(path), "read_only": True, "assets": []}
        assets = []
        connection = None
        try:
            connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
            query = """
                SELECT l.uid, l.title, l.category_name, l.category_path,
                       d.format, d.quality, d.path, d.cache_size
                FROM local_listing AS l
                LEFT JOIN download_meta AS d ON d.listing_uid = l.uid
                ORDER BY l.title COLLATE NOCASE
            """
            for row in connection.execute(query):
                asset = dict(row)
                asset["downloaded"] = bool(asset.get("path")) and Path(
                    str(asset.get("path"))
                ).exists()
                assets.append(asset)
        except sqlite3.Error as exc:
            return {
                "db_path": str(path),
                "read_only": True,
                "assets": [],
                "error": f"Fab library schema unavailable: {exc}",
            }
        finally:
            if connection is not None:
                connection.close()
        return {"db_path": str(path), "read_only": True, "assets": assets}

    def plan_download(
        self,
        asset_id: str,
        project_path: Union[str, Path],
        allowed_root: Union[str, Path],
        expected_price: Union[int, float] = 0,
        owned: bool = False,
    ) -> OperationResult:
        target = resolve_allowed_project(project_path, allowed_root)
        try:
            require_free_asset(expected_price, owned)
        except ValueError as exc:
            return OperationResult(
                CapabilityState.HUMAN_REQUIRED,
                "fab.download",
                str(exc),
                {"asset_id": asset_id, "project_path": str(target)},
            )
        return OperationResult(
            CapabilityState.UNAVAILABLE,
            "fab.download",
            "Fab download requires a verified Epic integration bridge",
            {
                "asset_id": asset_id,
                "project_path": str(target),
                "next_step": "connect a supported Fab Integration or signed bridge",
            },
        )
