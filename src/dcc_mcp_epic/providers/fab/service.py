from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

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
_ALLOWED_SOURCE_EXTENSIONS = {
    ".fbx",
    ".glb",
    ".gltf",
    ".obj",
    ".usd",
    ".usda",
    ".usdc",
    ".usdz",
    ".mtl",
    ".bin",
    ".png",
    ".jpg",
    ".jpeg",
    ".tga",
    ".exr",
}


class FabService:
    """Fab boundary. It never emulates marketplace clicks or stores credentials."""

    @staticmethod
    def _is_relative_to(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    def capabilities(self) -> Dict[str, Any]:
        return {
            "search": CapabilityState.READ_ONLY.value,
            "search_request": "available_if_declared_read_only_hook",
            "asset_detail": CapabilityState.READ_ONLY.value,
            "asset_detail_request": "available_if_declared_read_only_hook",
            "library": CapabilityState.READ_ONLY.value,
            "library_request": "available_if_declared_read_only_hook",
            "library_sources": CapabilityState.READ_ONLY.value,
            "library_sources_request": "available_if_declared_read_only_hook",
            "library_sync_request": "available_if_declared_scoped_hook",
            "add_to_library": "available_if_declared_free_hook",
            "add_to_library_batch": "available_if_declared_free_hook",
            "download": "available_if_declared_owned_hook",
            "download_batch": "available_if_declared_owned_hook",
            "add_to_project": "available_if_declared_owned_hook",
            "add_to_project_batch": "available_if_declared_owned_hook",
            "download_status": CapabilityState.READ_ONLY.value,
            "download_status_request": "available_if_declared_read_only_hook",
            "download_status_batch_request": "available_if_declared_read_only_hook",
            "export": "available_if_declared_owned_hook",
            "import_cached": "available_if_owned_cached_or_source_download",
            "import_all_cached": "available_if_owned_cached_or_source_download",
            "import_inventory": CapabilityState.READ_ONLY.value,
            "import_inventory_request": "available_if_declared_read_only_hook",
            "launcher_probe": CapabilityState.READ_ONLY.value,
            "launcher_status_probe": CapabilityState.READ_ONLY.value,
            "launcher_status_request": "available_if_declared_read_only_hook",
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
                acquisition_join = "LEFT JOIN listing_acquisition AS a ON a.listing_uid = l.uid"
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
                asset["downloaded"] = (
                    bool(asset.get("path")) and Path(str(asset.get("path"))).exists()
                )
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

    @staticmethod
    def _database_path_list(
        database_path: Union[str, Path] = DEFAULT_FAB_LIBRARY_DB,
        database_paths: Optional[Sequence[Union[str, Path]]] = None,
    ) -> List[Path]:
        """Normalize one or more explicitly selected Fab index paths."""

        values: Iterable[Union[str, Path]] = (
            database_paths if database_paths is not None else [database_path]
        )
        result: List[Path] = []
        seen = set()
        for value in values:
            path = Path(value).expanduser().resolve()
            key = str(path).casefold()
            if key not in seen:
                result.append(path)
                seen.add(key)
        return result

    def discover_library_databases(
        self,
        search_roots: Optional[Sequence[Union[str, Path]]] = None,
        *,
        max_depth: int = 6,
    ) -> Dict[str, Any]:
        """Find local Fab indexes below caller-approved roots without writing."""

        if max_depth < 0 or max_depth > 12:
            return {
                "operation": "fab.library_sources",
                "read_only": True,
                "databases": [],
                "error": "max_depth must be between 0 and 12",
            }
        roots = [DEFAULT_FAB_LIBRARY_DB.parent.parent]
        if search_roots:
            roots.extend(Path(item).expanduser() for item in search_roots)
        databases: List[Path] = []
        seen = set()
        for root_value in roots:
            root = root_value.resolve()
            if not root.is_dir() or root.is_symlink():
                continue
            for candidate in root.rglob("listings_v1.db"):
                if candidate.is_symlink() or not candidate.is_file():
                    continue
                try:
                    relative_depth = len(candidate.parent.relative_to(root).parts)
                except ValueError:
                    continue
                if relative_depth > max_depth:
                    continue
                resolved = candidate.resolve()
                key = str(resolved).casefold()
                if key not in seen:
                    databases.append(resolved)
                    seen.add(key)
        databases.sort(key=lambda value: str(value).casefold())
        return {
            "operation": "fab.library_sources",
            "read_only": True,
            "search_roots": [str(Path(item).expanduser().resolve()) for item in roots],
            "databases": [str(item) for item in databases],
        }

    def list_local_libraries(
        self,
        database_paths: Optional[Sequence[Union[str, Path]]] = None,
        *,
        search_roots: Optional[Sequence[Union[str, Path]]] = None,
        max_depth: int = 6,
    ) -> Dict[str, Any]:
        """Read and merge multiple Epic Fab indexes, preferring downloaded entries."""

        discovered = self.discover_library_databases(search_roots, max_depth=max_depth)
        paths = self._database_path_list(database_paths=database_paths)
        if database_paths is None:
            paths = [Path(item) for item in discovered.get("databases", [])]
        sources = []
        merged: Dict[str, Dict[str, Any]] = {}
        for path in paths:
            library = self.list_local_library(path)
            assets = library.get("assets", [])
            sources.append(
                {
                    "db_path": str(path),
                    "read_only": True,
                    "asset_count": len(assets),
                    "error": library.get("error"),
                }
            )
            for asset in assets:
                uid = str(asset.get("uid") or "")
                if not uid:
                    continue
                candidate = {**asset, "database_path": str(path)}
                current = merged.get(uid)
                if current is None:
                    merged[uid] = candidate
                    continue
                current_score = (
                    bool(current.get("owned")),
                    bool(current.get("downloaded")),
                    bool(current.get("path")),
                    bool(str(current.get("title") or "").strip()),
                    bool(str(current.get("format") or "").strip()),
                )
                candidate_score = (
                    bool(candidate.get("owned")),
                    bool(candidate.get("downloaded")),
                    bool(candidate.get("path")),
                    bool(str(candidate.get("title") or "").strip()),
                    bool(str(candidate.get("format") or "").strip()),
                )
                if candidate_score > current_score:
                    merged[uid] = candidate
        assets = sorted(merged.values(), key=lambda item: str(item.get("title", "")).casefold())
        return {
            "operation": "fab.library_sources",
            "read_only": True,
            "database_count": len(sources),
            "unique_asset_count": len(assets),
            "owned_downloaded_count": sum(
                1 for item in assets if item.get("owned") and item.get("downloaded")
            ),
            "not_downloaded_count": sum(1 for item in assets if not item.get("downloaded")),
            "sources": sources,
            "assets": assets,
        }

    def search_local_library(
        self,
        query: str = "",
        database_paths: Optional[Sequence[Union[str, Path]]] = None,
        *,
        search_roots: Optional[Sequence[Union[str, Path]]] = None,
        category: str = "",
        formats: Optional[Sequence[str]] = None,
        owned_only: bool = False,
        downloaded_only: bool = False,
        max_depth: int = 6,
    ) -> Dict[str, Any]:
        """Search the merged local Fab indexes without contacting Fab."""

        normalized_query = str(query or "").strip().casefold()
        normalized_category = str(category or "").strip().casefold()
        normalized_formats = {
            str(value).strip().casefold() for value in (formats or []) if str(value).strip()
        }
        library = self.list_local_libraries(
            database_paths,
            search_roots=search_roots,
            max_depth=max_depth,
        )
        matches = []
        for asset in library.get("assets", []):
            searchable = " ".join(
                str(asset.get(key) or "")
                for key in ("uid", "title", "category_name", "category_path")
            ).casefold()
            if normalized_query and normalized_query not in searchable:
                continue
            if (
                normalized_category
                and normalized_category
                not in " ".join(
                    str(asset.get(key) or "") for key in ("category_name", "category_path")
                ).casefold()
            ):
                continue
            if (
                normalized_formats
                and str(asset.get("format") or "").casefold() not in normalized_formats
            ):
                continue
            if owned_only and not asset.get("owned"):
                continue
            if downloaded_only and not asset.get("downloaded"):
                continue
            matches.append(asset)
        return {
            "operation": "fab.search",
            "read_only": True,
            "query": query,
            "category": category,
            "formats": sorted(normalized_formats),
            "owned_only": owned_only,
            "downloaded_only": downloaded_only,
            "database_count": library.get("database_count", 0),
            "result_count": len(matches),
            "assets": matches,
            "sources": library.get("sources", []),
        }

    def inspect_local_asset(
        self, asset_id: str, database_path: Union[str, Path] = DEFAULT_FAB_LIBRARY_DB
    ) -> Dict[str, Any]:
        """Return one locally indexed asset and its cached download metadata."""

        library = self.list_local_library(database_path)
        for asset in library.get("assets", []):
            if asset.get("uid") == asset_id:
                return {**library, "asset": asset}
        return {**library, "asset": None, "reason": "asset is not present in the local index"}

    def inspect_download_state(
        self,
        asset_id: str,
        database_path: Union[str, Path] = DEFAULT_FAB_LIBRARY_DB,
        *,
        cache_roots: Optional[Sequence[Union[str, Path]]] = None,
    ) -> Dict[str, Any]:
        """Re-read one Fab entry and report download evidence without mutation."""

        inspected = self.inspect_local_asset(asset_id, database_path)
        asset = inspected.get("asset")
        result: Dict[str, Any] = {
            "operation": "fab.download_status",
            "read_only": True,
            "asset_id": asset_id,
            "database_path": inspected.get("db_path"),
            "state": "not_indexed",
            "downloaded": False,
            "owned": False,
            "path": None,
            "path_exists": False,
            "cache_path_verified": False,
        }
        if not asset:
            result["reason"] = "asset is not present in the local index"
            return result
        result.update(
            {
                "title": asset.get("title"),
                "format": asset.get("format"),
                "quality": asset.get("quality"),
                "owned": bool(asset.get("owned")),
                "downloaded": bool(asset.get("downloaded")),
                "path": asset.get("path"),
                "cache_size": asset.get("cache_size"),
            }
        )
        source_value = asset.get("path")
        if not source_value:
            result["state"] = "owned_not_downloaded" if result["owned"] else "not_owned"
            return result
        source = Path(str(source_value)).expanduser().resolve()
        result["path"] = str(source)
        result["path_exists"] = source.exists()
        approved_roots = [DEFAULT_FAB_CACHE_ROOT.expanduser().resolve()]
        if cache_roots:
            approved_roots.extend(Path(item).expanduser().resolve() for item in cache_roots)
        result["cache_path_verified"] = any(
            self._is_relative_to(source, root) for root in approved_roots
        )
        if not result["cache_path_verified"]:
            result["state"] = "path_outside_approved_cache"
            return result
        if result["downloaded"] and result["path_exists"]:
            result["state"] = "downloaded"
        elif result["owned"]:
            result["state"] = "owned_path_missing"
        else:
            result["state"] = "not_owned"
        return result

    def inspect_download_states(
        self,
        asset_ids: Sequence[str],
        database_paths: Optional[Sequence[Union[str, Path]]] = None,
        *,
        search_roots: Optional[Sequence[Union[str, Path]]] = None,
        cache_roots: Optional[Sequence[Union[str, Path]]] = None,
        max_depth: int = 6,
    ) -> Dict[str, Any]:
        """Read download evidence for a bounded set of assets.

        Multiple Launcher profiles can leave more than one ``listings_v1.db``
        on disk. We inspect every explicitly selected/discovered index and
        retain the strongest evidence per asset, preferring a verified
        downloaded path over ownership-only or missing-index results.
        """

        values = [str(item).strip() for item in asset_ids if str(item).strip()]
        if not values:
            return {
                "operation": "fab.download_status_batch",
                "read_only": True,
                "assets": [],
                "error": "asset_ids must contain at least one non-empty id",
            }
        if len(values) > 100:
            return {
                "operation": "fab.download_status_batch",
                "read_only": True,
                "assets": [],
                "error": "asset_ids is limited to 100 entries per request",
            }
        if len(set(values)) != len(values):
            return {
                "operation": "fab.download_status_batch",
                "read_only": True,
                "assets": [],
                "error": "asset_ids must not contain duplicates",
            }
        if database_paths is None:
            discovered = self.discover_library_databases(search_roots, max_depth=max_depth)
            if discovered.get("error"):
                return discovered
            paths = [Path(item) for item in discovered.get("databases", [])]
            if not paths:
                paths = [DEFAULT_FAB_LIBRARY_DB]
        else:
            paths = self._database_path_list(database_paths=database_paths)
        rank = {
            "downloaded": 4,
            "owned_path_missing": 3,
            "owned_not_downloaded": 2,
            "path_outside_approved_cache": 1,
            "not_owned": 1,
            "not_indexed": 0,
        }
        selected: Dict[str, Dict[str, Any]] = {}
        candidate_counts: Dict[str, int] = {asset_id: 0 for asset_id in values}
        for database_path in paths:
            for asset_id in values:
                status = self.inspect_download_state(
                    asset_id, database_path, cache_roots=cache_roots
                )
                if status.get("state") != "not_indexed":
                    candidate_counts[asset_id] += 1
                current = selected.get(asset_id)
                if current is None or rank.get(status.get("state", ""), 0) > rank.get(
                    current.get("state", ""), 0
                ):
                    selected[asset_id] = status
        assets = []
        for asset_id in values:
            status = dict(
                selected.get(
                    asset_id,
                    {
                        "operation": "fab.download_status",
                        "read_only": True,
                        "asset_id": asset_id,
                        "state": "not_indexed",
                        "downloaded": False,
                        "owned": False,
                        "path": None,
                        "path_exists": False,
                        "cache_path_verified": False,
                    },
                )
            )
            status["candidate_count"] = candidate_counts[asset_id]
            assets.append(status)
        return {
            "operation": "fab.download_status_batch",
            "read_only": True,
            "database_count": len(paths),
            "asset_count": len(assets),
            "downloaded_count": sum(1 for item in assets if item.get("downloaded")),
            "owned_count": sum(1 for item in assets if item.get("owned")),
            "assets": assets,
        }

    def plan_download(
        self,
        asset_id: str,
        project_path: Union[str, Path],
        allowed_root: Union[str, Path],
        expected_price: Union[int, float] = 0,
        owned: bool = False,
    ) -> OperationResult:
        try:
            target = resolve_allowed_project(project_path, allowed_root)
        except ValueError as exc:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.download",
                str(exc),
                {"asset_id": asset_id, "side_effects_performed": False},
            )
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
        cache_roots: Optional[Sequence[Union[str, Path]]] = None,
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> OperationResult:
        """Plan or import an already downloaded, owned Unreal Fab asset.

        This operation deliberately does not contact Fab or modify Epic's cache
        database. It copies Unreal ``Content`` packages or supported source
        files from a cache path indexed by Epic's read-only library database and
        records provenance in a project-local manifest. Existing imported
        content is never overwritten.
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
        approved_cache_roots = [DEFAULT_FAB_CACHE_ROOT.expanduser().resolve()]
        if cache_roots:
            approved_cache_roots.extend(Path(item).expanduser().resolve() for item in cache_roots)
        unique_cache_roots: List[Path] = []
        seen_cache_roots = set()
        for cache_root in approved_cache_roots:
            key = str(cache_root).casefold()
            if key not in seen_cache_roots:
                unique_cache_roots.append(cache_root)
                seen_cache_roots.add(key)
        source = Path(str(source_value)).expanduser().resolve()
        if not any(self._is_relative_to(source, cache_root) for cache_root in unique_cache_roots):
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.import_cached_asset",
                "cache path is outside Epic's approved VaultCache roots",
                {
                    "asset_id": asset_id,
                    "cache_roots": [str(item) for item in unique_cache_roots],
                    "source": str(source),
                    "side_effects_performed": False,
                },
            )
        content = source / "data" / "Content"
        import_mode = "unreal-content"
        if not content.is_dir():
            content = source / "Content"
        if not content.is_dir():
            # Fab also stores FBX/GLTF/OBJ/USD downloads as source files rather
            # than Unreal Content packages. Preserve those files and textures
            # under Content/Fab so Unreal can import them on the next scan.
            import_mode = "source-files"
            content = source.parent if source.is_file() else source
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
            allowed_extensions = (
                _ALLOWED_CONTENT_EXTENSIONS
                if import_mode == "unreal-content"
                else _ALLOWED_SOURCE_EXTENSIONS
            )
            if candidate.suffix.lower() not in allowed_extensions:
                continue
            size = candidate.stat().st_size
            files.append({"path": relative.as_posix(), "size": size})
            total_bytes += size
        if not files:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.import_cached_asset",
                "cached asset contains no supported Unreal or source files",
                {"asset_id": asset_id, "source": str(source), "side_effects_performed": False},
            )

        title = str(asset.get("title") or asset_id)
        slug = "".join(char if char.isalnum() or char in "-_" else "_" for char in title).strip(
            "._"
        )
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
            "import_mode": import_mode,
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
        database_paths: Optional[Sequence[Union[str, Path]]] = None,
        cache_roots: Optional[Sequence[Union[str, Path]]] = None,
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """Plan/import every downloaded and owned local Fab Unreal asset."""

        paths = self._database_path_list(database_path, database_paths)
        results = []
        library = self.list_local_libraries(paths)
        for asset in library.get("assets", []):
            asset_id = str(asset.get("uid") or "")
            source_database = asset.get("database_path")
            if (
                not asset_id
                or not isinstance(source_database, str)
                or not asset.get("owned")
                or not asset.get("downloaded")
            ):
                continue
            result = self.plan_import_cached_asset(
                asset_id,
                project_path,
                allowed_root,
                source_database,
                cache_roots=cache_roots,
                confirmed=confirmed,
                dry_run=dry_run,
            )
            results.append(result.as_dict())
        return {
            "operation": "fab.import_all_cached",
            "database_paths": [str(item) for item in paths],
            "count": len(results),
            "results": results,
            "side_effects_performed": any(
                item.get("details", {}).get("side_effects_performed") for item in results
            ),
        }

    def project_import_inventory(
        self,
        project_path: Union[str, Path],
        allowed_root: Union[str, Path],
        *,
        destination_subdir: str = "Fab",
    ) -> Dict[str, Any]:
        """Audit project-local Fab import manifests and their file hashes."""

        try:
            project = resolve_allowed_project(project_path, allowed_root)
        except ValueError as exc:
            return {
                "operation": "fab.import_inventory",
                "read_only": True,
                "all_valid": False,
                "error": str(exc),
                "assets": [],
            }
        if project.suffix.lower() == ".uproject":
            project = project.parent
        if Path(destination_subdir).is_absolute() or ".." in Path(destination_subdir).parts:
            return {
                "operation": "fab.import_inventory",
                "read_only": True,
                "all_valid": False,
                "error": "destination_subdir must be a relative path without traversal",
                "project_path": str(project),
                "assets": [],
            }
        root = project / "Content" / destination_subdir
        if not root.is_dir():
            return {
                "operation": "fab.import_inventory",
                "read_only": True,
                "project_path": str(project),
                "root": str(root),
                "asset_count": 0,
                "file_count": 0,
                "total_bytes": 0,
                "all_valid": True,
                "assets": [],
            }

        assets = []
        for manifest_path in sorted(root.rglob(_IMPORT_MANIFEST)):
            record: Dict[str, Any] = {
                "manifest": str(manifest_path),
                "asset_id": None,
                "file_count": 0,
                "total_bytes": 0,
                "valid": False,
                "missing_files": [],
                "mismatched_files": [],
            }
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest.get("schema") != "dcc-mcp-epic.fab-import.v1":
                    raise ValueError("unsupported provenance schema")
                record["asset_id"] = str(manifest.get("asset_id") or "")
                files = manifest.get("files")
                if not isinstance(files, list) or not files:
                    raise ValueError("provenance manifest has no files")
                valid = True
                for item in files:
                    if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                        valid = False
                        record["mismatched_files"].append("<invalid-entry>")
                        continue
                    relative = Path(item["path"])
                    if relative.is_absolute() or ".." in relative.parts:
                        valid = False
                        record["mismatched_files"].append(item["path"])
                        continue
                    target = (manifest_path.parent / relative).resolve()
                    try:
                        target.relative_to(manifest_path.parent.resolve())
                    except ValueError:
                        valid = False
                        record["mismatched_files"].append(item["path"])
                        continue
                    if not target.is_file() or target.is_symlink():
                        valid = False
                        record["missing_files"].append(item["path"])
                        continue
                    actual_size = target.stat().st_size
                    record["file_count"] += 1
                    record["total_bytes"] += actual_size
                    expected_size = item.get("size")
                    expected_hash = item.get("sha256")
                    if (
                        not isinstance(expected_size, int)
                        or actual_size != expected_size
                        or not isinstance(expected_hash, str)
                        or hashlib.sha256(target.read_bytes()).hexdigest() != expected_hash
                    ):
                        valid = False
                        record["mismatched_files"].append(item["path"])
                record["valid"] = valid
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                record["error"] = str(exc)
            assets.append(record)
        return {
            "operation": "fab.import_inventory",
            "read_only": True,
            "project_path": str(project),
            "root": str(root),
            "asset_count": len(assets),
            "file_count": sum(item["file_count"] for item in assets),
            "total_bytes": sum(item["total_bytes"] for item in assets),
            "all_valid": all(item.get("valid") for item in assets),
            "assets": assets,
        }
