from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
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
DEFAULT_FAB_CACHE_ROOT = DEFAULT_FAB_LIBRARY_DB.parent.parent
_IMPORT_MANIFEST = ".dcc-mcp-fab.json"
_ALLOWED_CONTENT_EXTENSIONS = {
    ".uasset",
    ".umap",
    ".ubulk",
    ".uexp",
    ".ufont",
    ".utxt",
}


class FabService:
    """Fab boundary. It never emulates marketplace clicks or stores credentials."""

    def capabilities(self) -> Dict[str, Any]:
        return {
            "search": CapabilityState.UNAVAILABLE.value,
            "library": CapabilityState.READ_ONLY.value,
            "download": CapabilityState.UNAVAILABLE.value,
            "export": CapabilityState.UNAVAILABLE.value,
            "import_cached": "available_if_owned_cached",
            "import_all_cached": "available_if_owned_cached",
            "launcher_probe": CapabilityState.READ_ONLY.value,
            "launcher_status_probe": CapabilityState.READ_ONLY.value,
            "launcher_import": "available_if_bound_ue_editor",
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
            acquisition_join = ""
            owned_select = "0 AS owned"
            if connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='listing_acquisition'"
            ).fetchone():
                acquisition_join = (
                    "LEFT JOIN listing_acquisition AS a ON a.listing_uid = l.uid"
                )
                owned_select = "CASE WHEN a.listing_uid IS NULL THEN 0 ELSE 1 END AS owned"
            query = f"""
                SELECT l.uid, l.title, l.category_name, l.category_path,
                       {owned_select}, d.format, d.quality, d.path, d.cache_size
                FROM local_listing AS l
                LEFT JOIN download_meta AS d ON d.listing_uid = l.uid
                {acquisition_join}
                ORDER BY l.title COLLATE NOCASE
            """
            for row in connection.execute(query):
                asset = dict(row)
                asset["downloaded"] = bool(asset.get("path")) and Path(
                    str(asset.get("path"))
                ).exists()
                asset["owned"] = bool(asset.get("owned"))
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

    def inspect_local_asset(
        self, asset_id: str, database_path: Union[str, Path] = DEFAULT_FAB_LIBRARY_DB
    ) -> Dict[str, Any]:
        """Return one locally indexed asset and its cached download metadata."""

        library = self.list_local_library(database_path)
        for asset in library.get("assets", []):
            if asset.get("uid") == asset_id:
                return {**library, "asset": asset}
        return {**library, "asset": None, "reason": "asset is not present in the local index"}

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

    def plan_import_cached_asset(
        self,
        asset_id: str,
        project_path: Union[str, Path],
        allowed_root: Union[str, Path],
        database_path: Union[str, Path] = DEFAULT_FAB_LIBRARY_DB,
        *,
        destination_subdir: str = "Fab",
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> OperationResult:
        """Plan or import an already downloaded, owned Unreal Fab asset.

        This operation deliberately does not contact Fab or modify Epic's cache
        database. It copies only Unreal ``Content`` files from a cache path
        indexed by Epic's read-only library database and records provenance in a
        project-local manifest. Existing imported content is never overwritten.
        """

        project = resolve_allowed_project(project_path, allowed_root)
        if project.suffix.lower() == ".uproject":
            project = project.parent
        if not project.is_dir():
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.import_cached_asset",
                "project directory does not exist",
                {"project_path": str(project), "side_effects_performed": False},
            )
        if not asset_id.strip():
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.import_cached_asset",
                "asset_id must not be empty",
                {"project_path": str(project), "side_effects_performed": False},
            )
        if Path(destination_subdir).is_absolute() or ".." in Path(destination_subdir).parts:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.import_cached_asset",
                "destination_subdir must be a relative path without traversal",
                {"project_path": str(project), "side_effects_performed": False},
            )

        inspected = self.inspect_local_asset(asset_id, database_path)
        asset = inspected.get("asset")
        if not asset:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.import_cached_asset",
                "asset is not present in the local Fab index",
                {
                    "asset_id": asset_id,
                    "project_path": str(project),
                    "side_effects_performed": False,
                },
            )
        if not asset.get("owned"):
            return OperationResult(
                CapabilityState.HUMAN_REQUIRED,
                "fab.import_cached_asset",
                "local ownership is not verified by Epic's acquisition index",
                {
                    "asset_id": asset_id,
                    "project_path": str(project),
                    "side_effects_performed": False,
                },
            )
        source_value = asset.get("path")
        if not source_value:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.import_cached_asset",
                "asset has no downloaded cache path",
                {
                    "asset_id": asset_id,
                    "project_path": str(project),
                    "side_effects_performed": False,
                },
            )
        cache_root = DEFAULT_FAB_CACHE_ROOT.expanduser().resolve()
        source = Path(str(source_value)).expanduser().resolve()
        try:
            source.relative_to(cache_root)
        except ValueError:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.import_cached_asset",
                "cache path is outside Epic's approved VaultCache root",
                {
                    "asset_id": asset_id,
                    "cache_root": str(cache_root),
                    "source": str(source),
                    "side_effects_performed": False,
                },
            )
        content = source / "data" / "Content"
        if not content.is_dir():
            content = source / "Content"
        if not content.is_dir():
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.import_cached_asset",
                "cached asset does not contain an Unreal Content directory",
                {"asset_id": asset_id, "source": str(source), "side_effects_performed": False},
            )
        files = []
        total_bytes = 0
        for candidate in sorted(content.rglob("*")):
            if not candidate.is_file() or candidate.is_symlink():
                continue
            resolved = candidate.resolve()
            try:
                relative = resolved.relative_to(content.resolve())
            except ValueError:
                return OperationResult(
                    CapabilityState.UNAVAILABLE,
                    "fab.import_cached_asset",
                    "cached asset contains a file outside its Content root",
                    {"asset_id": asset_id, "file": str(candidate), "side_effects_performed": False},
                )
            if candidate.suffix.lower() not in _ALLOWED_CONTENT_EXTENSIONS:
                continue
            size = candidate.stat().st_size
            files.append({"path": relative.as_posix(), "size": size})
            total_bytes += size
        if not files:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.import_cached_asset",
                "cached asset contains no supported Unreal content files",
                {"asset_id": asset_id, "source": str(source), "side_effects_performed": False},
            )

        title = str(asset.get("title") or asset_id)
        slug = "".join(
            char if char.isalnum() or char in "-_" else "_" for char in title
        ).strip("._")
        slug = (slug or "asset")[:80]
        destination = project / "Content" / destination_subdir / f"{slug}-{asset_id[:8]}"
        try:
            destination.relative_to(project.resolve())
        except ValueError:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.import_cached_asset",
                "resolved destination is outside the project",
                {
                    "asset_id": asset_id,
                    "destination": str(destination),
                    "side_effects_performed": False,
                },
            )
        details = {
            "asset_id": asset_id,
            "title": title,
            "source": str(source),
            "content_root": str(content),
            "project_path": str(project),
            "destination": str(destination),
            "file_count": len(files),
            "total_bytes": total_bytes,
            "files": files,
            "owned": True,
            "price_verified": False,
            "license_note": (
                "Import uses an already-owned local cache; verify Fab license terms "
                "for the project."
            ),
            "side_effects_performed": False,
        }
        if destination.exists():
            manifest = destination / _IMPORT_MANIFEST
            if manifest.is_file():
                try:
                    existing = json.loads(manifest.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    existing = {}
                if existing.get("asset_id") == asset_id and existing.get("source") == str(source):
                    details["already_imported"] = True
                    return OperationResult(
                        CapabilityState.AVAILABLE,
                        "fab.import_cached_asset",
                        "asset is already imported and was not changed",
                        details,
                    )
            return OperationResult(
                CapabilityState.HUMAN_REQUIRED,
                "fab.import_cached_asset",
                "destination exists without a matching provenance manifest; refusing overwrite",
                details,
            )
        if dry_run:
            return OperationResult(
                CapabilityState.READ_ONLY,
                "fab.import_cached_asset",
                "cached asset import plan created; dry-run performed",
                details,
            )
        if not confirmed:
            return OperationResult(
                CapabilityState.HUMAN_REQUIRED,
                "fab.import_cached_asset",
                "cached asset import requires explicit confirmation",
                details,
            )

        staging_parent = project / ".dcc-mcp-staging"
        staging = staging_parent / f"fab-{asset_id[:8]}-{uuid.uuid4().hex}"
        try:
            staging.mkdir(parents=True, exist_ok=False)
            copied = []
            for file_info in files:
                relative = Path(file_info["path"])
                source_file = content / relative
                target_file = staging / relative
                target_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_file, target_file)
                digest = hashlib.sha256(target_file.read_bytes()).hexdigest()
                copied.append({**file_info, "sha256": digest})
            provenance = {
                "schema": "dcc-mcp-epic.fab-import.v1",
                "asset_id": asset_id,
                "title": title,
                "source": str(source),
                "library_db": str(Path(database_path).expanduser().resolve()),
                "imported_at": datetime.now(timezone.utc).isoformat(),
                "files": copied,
            }
            (staging / _IMPORT_MANIFEST).write_text(
                json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            staging.rename(destination)
        except (OSError, ValueError) as exc:
            shutil.rmtree(staging, ignore_errors=True)
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.import_cached_asset",
                f"cached asset import failed: {exc}",
                details,
            )
        finally:
            if staging_parent.is_dir() and not any(staging_parent.iterdir()):
                staging_parent.rmdir()
        details["side_effects_performed"] = True
        details["import_manifest"] = str(destination / _IMPORT_MANIFEST)
        details["files"] = copied
        return OperationResult(
            CapabilityState.AVAILABLE,
            "fab.import_cached_asset",
            "cached asset imported into the Unreal project",
            details,
        )

    def import_all_cached_assets(
        self,
        project_path: Union[str, Path],
        allowed_root: Union[str, Path],
        database_path: Union[str, Path] = DEFAULT_FAB_LIBRARY_DB,
        *,
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """Plan/import every downloaded and owned local Fab Unreal asset."""

        library = self.list_local_library(database_path)
        results = []
        for asset in library.get("assets", []):
            if not asset.get("owned") or not asset.get("downloaded"):
                continue
            result = self.plan_import_cached_asset(
                str(asset["uid"]),
                project_path,
                allowed_root,
                database_path,
                confirmed=confirmed,
                dry_run=dry_run,
            )
            results.append(result.as_dict())
        return {
            "operation": "fab.import_all_cached",
            "database_path": str(Path(database_path).expanduser().resolve()),
            "count": len(results),
            "results": results,
            "side_effects_performed": any(
                item.get("details", {}).get("side_effects_performed") for item in results
            ),
        }
