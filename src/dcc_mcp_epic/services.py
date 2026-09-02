from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Union

import psutil

from .hooks import HOOK_OPERATIONS, invoke_hook, load_hook_manifest, probe_hook
from .models import CapabilityState, LauncherBinding, OperationResult
from .policy import require_free_asset, require_free_listing, resolve_allowed_project
from .providers.epic_launcher.manifest import DEFAULT_MANIFEST_ROOT, list_engine_installs
from .providers.epic_launcher.runtime import bind_launcher
from .providers.fab.bridge import DEFAULT_FAB_STATUS_PORT, probe_fab_status_listener
from .providers.fab.service import DEFAULT_FAB_LIBRARY_DB, FabService
from .providers.unreal.project import verify_project


class EpicService:
    def __init__(self) -> None:
        self.fab = FabService()

    def capabilities(self) -> Dict[str, Any]:
        return {
            "adapter": "dcc-mcp-epic",
            "contract_version": "epic.adapter.v1",
            "engine.list_installed": CapabilityState.READ_ONLY.value,
            "engine.update": CapabilityState.HUMAN_REQUIRED.value,
            "engine.download": CapabilityState.HUMAN_REQUIRED.value,
            "engine.launch": CapabilityState.READ_ONLY.value,
            "engine.verify": CapabilityState.READ_ONLY.value,
            "launcher.status_request": "available_if_declared_read_only_hook",
            "engine.install.request": "available_if_declared_hook",
            "engine.update.request": "available_if_declared_hook",
            "engine.download.request": "available_if_declared_hook",
            "engine.verify.request": "available_if_declared_hook",
            "engine.launch.request": "available_if_declared_hook",
            "fab": self.fab.capabilities(),
            "project.verify": CapabilityState.READ_ONLY.value,
            "hooks": {
                "probe": CapabilityState.READ_ONLY.value,
                "invoke": "available_if_declared",
                "protocol": "epic.hook.v1",
                "contract_tool": "epic_hook_contract",
                "operations": sorted(HOOK_OPERATIONS),
            },
            "cua_fallback": False,
        }

    def launcher_status(self, binding: LauncherBinding) -> Dict[str, Any]:
        return bind_launcher(binding).status()

    def launcher_status_request(
        self,
        binding: LauncherBinding,
        hook_manifest: Union[str, Path],
        *,
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> OperationResult:
        """Route exact Launcher status evidence through a read-only hook.

        The adapter still binds the caller supplied PID/HWND/executable before
        invoking the hook.  A hook can therefore replace the Launcher-specific
        status implementation without receiving an unscoped process selector.
        """

        try:
            status = self.launcher_status(binding)
        except (OSError, ValueError, psutil.Error) as exc:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "launcher.status",
                f"Launcher binding failed: {exc}",
                {"binding": binding.as_dict(), "side_effects_performed": False},
            )
        payload = {
            "pid": int(binding.pid),
            "hwnd": int(binding.hwnd),
            "executable": str(binding.executable.expanduser().resolve()),
            "version": str(binding.version),
            "status": status,
        }
        return self._typed_hook_request(
            "launcher.status",
            hook_manifest,
            payload,
            confirmed=confirmed,
            dry_run=dry_run,
            plan=OperationResult(
                CapabilityState.READ_ONLY,
                "launcher.status",
                "exact Launcher binding status was read before invoking the hook",
                {"binding": binding.as_dict(), "status": status},
            ),
        )

    def list_engines(
        self, manifest_root: Union[str, Path] = DEFAULT_MANIFEST_ROOT
    ) -> Dict[str, Any]:
        entries = list_engine_installs(manifest_root)
        return {
            "manifest_root": str(Path(manifest_root).expanduser().resolve()),
            "read_only": True,
            "engines": [entry.as_dict() for entry in entries],
        }

    def engine_update_plan(
        self, target_version: str, manifest_root: Union[str, Path]
    ) -> OperationResult:
        engines = list_engine_installs(manifest_root)
        matches = [item for item in engines if item.app_name == f"UE_{target_version}"]
        return OperationResult(
            CapabilityState.HUMAN_REQUIRED,
            "engine.update",
            "Launcher update requires a supported native bridge and user confirmation",
            {
                "target_version": target_version,
                "already_installed": [item.as_dict() for item in matches],
                "manifest_read_only": True,
                "side_effects_performed": False,
            },
        )

    def engine_download_plan(
        self, target_version: str, manifest_root: Union[str, Path]
    ) -> OperationResult:
        return OperationResult(
            CapabilityState.HUMAN_REQUIRED,
            "engine.download",
            "Launcher download requires a supported native bridge and user confirmation",
            {
                "target_version": target_version,
                "manifest_root": str(Path(manifest_root).expanduser().resolve()),
                "manifest_read_only": True,
                "side_effects_performed": False,
            },
        )

    def engine_launch_plan(
        self,
        target_version: str,
        project_path: Union[str, Path],
        manifest_root: Union[str, Path],
    ) -> OperationResult:
        engines = list_engine_installs(manifest_root)
        match = next((item for item in engines if item.app_name == f"UE_{target_version}"), None)
        if match is None:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "engine.launch",
                "requested Unreal Engine version is not installed",
                {"target_version": target_version, "side_effects_performed": False},
            )
        editor = match.install_location / "Engine" / "Binaries" / "Win64" / "UnrealEditor.exe"
        return OperationResult(
            CapabilityState.READ_ONLY if editor.is_file() else CapabilityState.UNAVAILABLE,
            "engine.launch",
            "launch plan created; execution remains an explicit bridge operation",
            {
                "target_version": target_version,
                "editor_path": str(editor),
                "project_path": str(Path(project_path).expanduser().resolve()),
                "editor_exists": editor.is_file(),
                "side_effects_performed": False,
            },
        )

    def verify_engines(self, manifest_root: Union[str, Path]) -> Dict[str, Any]:
        entries = list_engine_installs(manifest_root)
        checks = []
        for entry in entries:
            editor = entry.install_location / "Engine" / "Binaries" / "Win64" / "UnrealEditor.exe"
            checks.append(
                {
                    "app_name": entry.app_name,
                    "version": entry.version,
                    "install_location": str(entry.install_location),
                    "editor_path": str(editor),
                    "editor_exists": editor.is_file(),
                    "manifest_path": str(entry.manifest_path),
                }
            )
        return {
            "manifest_root": str(Path(manifest_root).expanduser().resolve()),
            "read_only": True,
            "all_valid": all(item["editor_exists"] for item in checks),
            "engines": checks,
        }

    def verify_project(
        self, project_path: Union[str, Path], expected_engine: str = "5.5"
    ) -> Dict[str, Any]:
        return verify_project(project_path, expected_engine)

    def hook_probe(self, manifest_path: Union[str, Path]) -> Dict[str, Any]:
        return probe_hook(load_hook_manifest(manifest_path))

    def hook_invoke(
        self,
        manifest_path: Union[str, Path],
        operation: str,
        payload: Dict[str, Any],
        *,
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> OperationResult:
        return invoke_hook(
            load_hook_manifest(manifest_path),
            operation,
            payload,
            confirmed=confirmed,
            dry_run=dry_run,
        )

    @staticmethod
    def _scoped_path(
        value: Union[str, Path], allowed_root: Optional[Union[str, Path]], field: str
    ) -> tuple[Optional[Path], Optional[OperationResult]]:
        """Resolve a hook path only when its caller supplied an approved root."""

        if allowed_root is None:
            return None, OperationResult(
                CapabilityState.HUMAN_REQUIRED,
                "hook.request",
                f"{field} requires an explicit allowed_root",
                {"field": field, "side_effects_performed": False},
            )
        try:
            return resolve_allowed_project(value, allowed_root), None
        except ValueError as exc:
            return None, OperationResult(
                CapabilityState.UNAVAILABLE,
                "hook.request",
                str(exc),
                {"field": field, "side_effects_performed": False},
            )

    def _typed_hook_request(
        self,
        operation: str,
        hook_manifest: Union[str, Path],
        payload: Dict[str, Any],
        *,
        confirmed: bool,
        dry_run: bool,
        plan: Optional[OperationResult] = None,
    ) -> OperationResult:
        """Dispatch a declared operation while retaining the preflight plan."""

        result = self.hook_invoke(
            hook_manifest,
            operation,
            payload,
            confirmed=confirmed,
            dry_run=dry_run,
        )
        details = dict(result.details)
        details["payload"] = payload if dry_run else details.get("payload")
        if plan is not None:
            details["plan"] = plan.as_dict()
        details.setdefault("side_effects_performed", False)
        return OperationResult(
            result.state,
            operation,
            f"typed {operation} hook request processed; verify the resulting state",
            details,
        )

    def engine_install_request(
        self,
        target_version: str,
        hook_manifest: Union[str, Path],
        *,
        install_root: Optional[Union[str, Path]] = None,
        allowed_root: Optional[Union[str, Path]] = None,
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> OperationResult:
        if allowed_root is None:
            return OperationResult(
                CapabilityState.HUMAN_REQUIRED,
                "engine.install.request",
                "engine install requires an explicit allowed_root",
                {"side_effects_performed": False},
            )
        payload: Dict[str, Any] = {"target_version": str(target_version)}
        if install_root is not None:
            path, error = self._scoped_path(install_root, allowed_root, "install_root")
            if error:
                return OperationResult(
                    error.state,
                    "engine.install.request",
                    error.message,
                    error.details,
                )
            payload["install_root"] = str(path)
        else:
            payload["allowed_root"] = str(Path(allowed_root).expanduser().resolve())
        return self._typed_hook_request(
            "engine.install.request",
            hook_manifest,
            payload,
            confirmed=confirmed,
            dry_run=dry_run,
        )

    def engine_update_request(
        self,
        target_version: str,
        hook_manifest: Union[str, Path],
        *,
        manifest_root: Union[str, Path] = DEFAULT_MANIFEST_ROOT,
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> OperationResult:
        plan = self.engine_update_plan(target_version, manifest_root)
        payload = {
            "target_version": str(target_version),
            "manifest_root": str(Path(manifest_root).expanduser().resolve()),
        }
        return self._typed_hook_request(
            "engine.update.request",
            hook_manifest,
            payload,
            confirmed=confirmed,
            dry_run=dry_run,
            plan=plan,
        )

    def engine_download_request(
        self,
        target_version: str,
        hook_manifest: Union[str, Path],
        *,
        install_root: Optional[Union[str, Path]] = None,
        allowed_root: Optional[Union[str, Path]] = None,
        manifest_root: Union[str, Path] = DEFAULT_MANIFEST_ROOT,
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> OperationResult:
        if allowed_root is None:
            return OperationResult(
                CapabilityState.HUMAN_REQUIRED,
                "engine.download.request",
                "engine download requires an explicit allowed_root",
                {"side_effects_performed": False},
            )
        plan = self.engine_download_plan(target_version, manifest_root)
        payload: Dict[str, Any] = {
            "target_version": str(target_version),
            "manifest_root": str(Path(manifest_root).expanduser().resolve()),
        }
        if install_root is not None:
            path, error = self._scoped_path(install_root, allowed_root, "install_root")
            if error:
                return OperationResult(
                    error.state,
                    "engine.download.request",
                    error.message,
                    error.details,
                )
            payload["install_root"] = str(path)
        else:
            payload["allowed_root"] = str(Path(allowed_root).expanduser().resolve())
        return self._typed_hook_request(
            "engine.download.request",
            hook_manifest,
            payload,
            confirmed=confirmed,
            dry_run=dry_run,
            plan=plan,
        )

    def engine_verify_request(
        self,
        hook_manifest: Union[str, Path],
        *,
        manifest_root: Union[str, Path] = DEFAULT_MANIFEST_ROOT,
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> OperationResult:
        payload = {"manifest_root": str(Path(manifest_root).expanduser().resolve())}
        return self._typed_hook_request(
            "engine.verify.request",
            hook_manifest,
            payload,
            confirmed=confirmed,
            dry_run=dry_run,
            plan=OperationResult(
                CapabilityState.READ_ONLY,
                "engine.verify",
                "local engine verification can be read before invoking the hook",
                self.verify_engines(manifest_root),
            ),
        )

    def engine_launch_request(
        self,
        target_version: str,
        project_path: Union[str, Path],
        allowed_root: Union[str, Path],
        hook_manifest: Union[str, Path],
        *,
        manifest_root: Union[str, Path] = DEFAULT_MANIFEST_ROOT,
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> OperationResult:
        try:
            project = resolve_allowed_project(project_path, allowed_root)
        except ValueError as exc:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "engine.launch.request",
                str(exc),
                {"side_effects_performed": False},
            )
        plan = self.engine_launch_plan(target_version, project, manifest_root)
        if plan.state is CapabilityState.UNAVAILABLE:
            return OperationResult(
                plan.state,
                "engine.launch.request",
                plan.message,
                plan.details,
            )
        payload = {
            "target_version": str(target_version),
            "project_path": str(project),
            "allowed_root": str(Path(allowed_root).expanduser().resolve()),
            "manifest_root": str(Path(manifest_root).expanduser().resolve()),
        }
        return self._typed_hook_request(
            "engine.launch.request",
            hook_manifest,
            payload,
            confirmed=confirmed,
            dry_run=dry_run,
            plan=plan,
        )

    def fab_search_request(
        self,
        query: str,
        hook_manifest: Union[str, Path],
        *,
        database_paths: Optional[Sequence[Union[str, Path]]] = None,
        search_roots: Optional[Sequence[Union[str, Path]]] = None,
        category: str = "",
        formats: Optional[Sequence[str]] = None,
        owned_only: bool = False,
        downloaded_only: bool = False,
        max_depth: int = 6,
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> OperationResult:
        """Route a read-only Fab search through a user-owned provider hook."""

        plan = self.fab.search_local_library(
            query,
            database_paths,
            search_roots=search_roots,
            category=category,
            formats=formats,
            owned_only=owned_only,
            downloaded_only=downloaded_only,
            max_depth=max_depth,
        )
        payload: Dict[str, Any] = {
            "query": str(query or ""),
            "category": str(category or ""),
            "formats": [str(item) for item in (formats or [])],
            "owned_only": bool(owned_only),
            "downloaded_only": bool(downloaded_only),
            "max_depth": int(max_depth),
        }
        if database_paths:
            payload["database_paths"] = [
                str(Path(item).expanduser().resolve()) for item in database_paths
            ]
        if search_roots:
            payload["search_roots"] = [
                str(Path(item).expanduser().resolve()) for item in search_roots
            ]
        return self._typed_hook_request(
            "fab.search.request",
            hook_manifest,
            payload,
            confirmed=confirmed,
            dry_run=dry_run,
            plan=OperationResult(
                CapabilityState.READ_ONLY,
                "fab.search",
                "local Fab search was read before invoking the provider hook",
                plan,
            ),
        )

    def fab_library_request(
        self,
        hook_manifest: Union[str, Path],
        *,
        database_path: Optional[Union[str, Path]] = None,
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> OperationResult:
        """Route a read-only single-index Fab library read to a hook."""

        local = self.fab.list_local_library(database_path or DEFAULT_FAB_LIBRARY_DB)
        payload: Dict[str, Any] = {}
        if database_path is not None:
            payload["database_path"] = str(Path(database_path).expanduser().resolve())
        return self._typed_hook_request(
            "fab.library.request",
            hook_manifest,
            payload,
            confirmed=confirmed,
            dry_run=dry_run,
            plan=OperationResult(
                CapabilityState.READ_ONLY,
                "fab.library",
                "local Fab library was read before invoking the provider hook",
                local,
            ),
        )

    def fab_asset_detail_request(
        self,
        asset_id: str,
        hook_manifest: Union[str, Path],
        *,
        database_paths: Optional[Sequence[Union[str, Path]]] = None,
        search_roots: Optional[Sequence[Union[str, Path]]] = None,
        cache_roots: Optional[Sequence[Union[str, Path]]] = None,
        max_depth: int = 6,
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> OperationResult:
        """Route one local Fab listing and its cache evidence through a hook."""

        operation = "fab.asset_detail.request"
        normalized = str(asset_id or "").strip()
        if not normalized:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                operation,
                "asset_id must not be empty",
                {"side_effects_performed": False},
            )
        local = self.fab.list_local_libraries(
            database_paths,
            search_roots=search_roots,
            max_depth=max_depth,
        )
        matches = [item for item in local.get("assets", []) if item.get("uid") == normalized]
        asset = matches[0] if matches else None
        status = None
        if asset is not None:
            status = self.fab.inspect_download_state(
                normalized,
                asset.get("database_path", DEFAULT_FAB_LIBRARY_DB),
                cache_roots=cache_roots,
            )
        payload: Dict[str, Any] = {"asset_id": normalized, "max_depth": int(max_depth)}
        if database_paths:
            payload["database_paths"] = [
                str(Path(item).expanduser().resolve()) for item in database_paths
            ]
        if search_roots:
            payload["search_roots"] = [
                str(Path(item).expanduser().resolve()) for item in search_roots
            ]
        if cache_roots:
            payload["cache_roots"] = [
                str(Path(item).expanduser().resolve()) for item in cache_roots
            ]
        return self._typed_hook_request(
            operation,
            hook_manifest,
            payload,
            confirmed=confirmed,
            dry_run=dry_run,
            plan=OperationResult(
                CapabilityState.READ_ONLY,
                "fab.asset_detail",
                "local Fab asset detail and cache evidence were read before invoking the hook",
                {"asset_id": normalized, "asset": asset, "download_status": status},
            ),
        )

    def fab_library_sources_request(
        self,
        hook_manifest: Union[str, Path],
        *,
        database_paths: Optional[Sequence[Union[str, Path]]] = None,
        search_roots: Optional[Sequence[Union[str, Path]]] = None,
        max_depth: int = 6,
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> OperationResult:
        """Route multi-index Fab discovery to a read-only provider hook."""

        local = self.fab.list_local_libraries(
            database_paths,
            search_roots=search_roots,
            max_depth=max_depth,
        )
        payload: Dict[str, Any] = {"max_depth": int(max_depth)}
        if database_paths:
            payload["database_paths"] = [
                str(Path(item).expanduser().resolve()) for item in database_paths
            ]
        if search_roots:
            payload["search_roots"] = [
                str(Path(item).expanduser().resolve()) for item in search_roots
            ]
        return self._typed_hook_request(
            "fab.library_sources.request",
            hook_manifest,
            payload,
            confirmed=confirmed,
            dry_run=dry_run,
            plan=OperationResult(
                CapabilityState.READ_ONLY,
                "fab.library_sources",
                "local Fab sources were discovered before invoking the provider hook",
                local,
            ),
        )

    def fab_download_status_request(
        self,
        asset_id: str,
        hook_manifest: Union[str, Path],
        *,
        database_path: Optional[Union[str, Path]] = None,
        cache_roots: Optional[Sequence[Union[str, Path]]] = None,
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> OperationResult:
        """Route fresh Fab ownership/download status to a read-only hook."""

        local = self.fab.inspect_download_state(
            asset_id,
            database_path or DEFAULT_FAB_LIBRARY_DB,
            cache_roots=cache_roots,
        )
        payload: Dict[str, Any] = {"asset_id": str(asset_id)}
        if database_path is not None:
            payload["database_path"] = str(Path(database_path).expanduser().resolve())
        if cache_roots:
            payload["cache_roots"] = [
                str(Path(item).expanduser().resolve()) for item in cache_roots
            ]
        return self._typed_hook_request(
            "fab.download_status.request",
            hook_manifest,
            payload,
            confirmed=confirmed,
            dry_run=dry_run,
            plan=OperationResult(
                CapabilityState.READ_ONLY,
                "fab.download_status",
                "local Fab download evidence was read before invoking the provider hook",
                local,
            ),
        )

    def fab_download_status_batch_request(
        self,
        asset_ids: Sequence[str],
        hook_manifest: Union[str, Path],
        *,
        database_paths: Optional[Sequence[Union[str, Path]]] = None,
        search_roots: Optional[Sequence[Union[str, Path]]] = None,
        cache_roots: Optional[Sequence[Union[str, Path]]] = None,
        max_depth: int = 6,
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> OperationResult:
        """Route bounded multi-asset download evidence through a hook."""

        operation = "fab.download_status_batch.request"
        values = [str(item).strip() for item in asset_ids if str(item).strip()]
        if not values:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                operation,
                "asset_ids must contain at least one non-empty id",
                {"side_effects_performed": False},
            )
        if len(values) > 100:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                operation,
                "asset_ids is limited to 100 entries per request",
                {"count": len(values), "side_effects_performed": False},
            )
        if len(set(values)) != len(values):
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                operation,
                "asset_ids must not contain duplicates",
                {"side_effects_performed": False},
            )
        local = self.fab.inspect_download_states(
            values,
            database_paths,
            search_roots=search_roots,
            cache_roots=cache_roots,
            max_depth=max_depth,
        )
        if local.get("error"):
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                operation,
                str(local["error"]),
                {"side_effects_performed": False},
            )
        payload: Dict[str, Any] = {
            "assets": [{"asset_id": asset_id} for asset_id in values],
            "max_depth": int(max_depth),
        }
        if database_paths:
            payload["database_paths"] = [
                str(Path(item).expanduser().resolve()) for item in database_paths
            ]
        if search_roots:
            payload["search_roots"] = [
                str(Path(item).expanduser().resolve()) for item in search_roots
            ]
        if cache_roots:
            payload["cache_roots"] = [
                str(Path(item).expanduser().resolve()) for item in cache_roots
            ]
        return self._typed_hook_request(
            operation,
            hook_manifest,
            payload,
            confirmed=confirmed,
            dry_run=dry_run,
            plan=OperationResult(
                CapabilityState.READ_ONLY,
                "fab.download_status_batch",
                "local Fab download evidence was read before invoking the hook",
                local,
            ),
        )

    def fab_add_to_library_request(
        self,
        asset_id: str,
        hook_manifest: Union[str, Path],
        *,
        expected_price: Union[int, float] = 0,
        free_listing: bool = False,
        launcher_pid: Optional[int] = None,
        launcher_hwnd: Optional[int] = None,
        launcher_executable: Optional[Union[str, Path]] = None,
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> OperationResult:
        """Add one explicitly-free Fab listing to the user's library.

        This is intentionally separate from ``fab.download``: adding to the
        library establishes account ownership and may require an Epic UI or
        official bridge.  The adapter only validates the free-price assertion
        and an optional exact Launcher identity; the declared hook performs
        the action and must return fresh ownership evidence.
        """

        operation = "fab.add_to_library.request"
        if not isinstance(asset_id, str) or not asset_id.strip():
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                operation,
                "asset_id must not be empty",
                {"side_effects_performed": False},
            )
        try:
            require_free_listing(expected_price, free_listing)
        except ValueError as exc:
            return OperationResult(
                CapabilityState.HUMAN_REQUIRED,
                operation,
                str(exc),
                {"asset_id": asset_id, "side_effects_performed": False},
            )
        binding_values = (launcher_pid, launcher_hwnd, launcher_executable)
        if any(value is not None for value in binding_values):
            if not all(value is not None for value in binding_values):
                return OperationResult(
                    CapabilityState.UNAVAILABLE,
                    operation,
                    "launcher_pid, launcher_hwnd, and launcher_executable must be "
                    "provided together",
                    {"asset_id": asset_id, "side_effects_performed": False},
                )
            if int(launcher_pid or 0) <= 0 or int(launcher_hwnd or 0) <= 0:
                return OperationResult(
                    CapabilityState.UNAVAILABLE,
                    operation,
                    "launcher_pid and launcher_hwnd must be positive",
                    {"asset_id": asset_id, "side_effects_performed": False},
                )
            executable = Path(launcher_executable).expanduser().resolve()
            if not executable.is_absolute() or not executable.is_file():
                return OperationResult(
                    CapabilityState.UNAVAILABLE,
                    operation,
                    "launcher_executable must be an existing absolute file",
                    {"asset_id": asset_id, "side_effects_performed": False},
                )
        else:
            executable = None
        payload: Dict[str, Any] = {
            "asset_id": asset_id.strip(),
            "expected_price": expected_price,
            "free_listing": True,
            "action": "add_to_library",
            "verification_required": (
                "re-read Epic/Fab ownership and local library evidence after the hook"
            ),
        }
        if launcher_pid is not None:
            payload["launcher_pid"] = int(launcher_pid)
            payload["launcher_hwnd"] = int(launcher_hwnd or 0)
            payload["launcher_executable"] = str(executable)
        return self._typed_hook_request(
            operation,
            hook_manifest,
            payload,
            confirmed=confirmed,
            dry_run=dry_run,
        )

    def fab_add_to_library_batch_request(
        self,
        asset_ids: Sequence[str],
        hook_manifest: Union[str, Path],
        *,
        expected_price: Union[int, float] = 0,
        free_listing: bool = False,
        launcher_pid: Optional[int] = None,
        launcher_hwnd: Optional[int] = None,
        launcher_executable: Optional[Union[str, Path]] = None,
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> OperationResult:
        """Dispatch a bounded per-asset Fab Add to My Library sequence."""

        operation = "fab.add_to_library_batch.request"
        try:
            require_free_listing(expected_price, free_listing)
        except ValueError as exc:
            return OperationResult(
                CapabilityState.HUMAN_REQUIRED,
                operation,
                str(exc),
                {"side_effects_performed": False},
            )
        values = [str(item).strip() for item in asset_ids if str(item).strip()]
        if not values:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                operation,
                "asset_ids must contain at least one non-empty id",
                {"side_effects_performed": False},
            )
        if len(values) > 100:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                operation,
                "asset_ids is limited to 100 entries per request",
                {"count": len(values), "side_effects_performed": False},
            )
        if len(set(values)) != len(values):
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                operation,
                "asset_ids must not contain duplicates",
                {"side_effects_performed": False},
            )
        binding_values = (launcher_pid, launcher_hwnd, launcher_executable)
        if any(value is not None for value in binding_values):
            if not all(value is not None for value in binding_values):
                return OperationResult(
                    CapabilityState.UNAVAILABLE,
                    operation,
                    "launcher_pid, launcher_hwnd, and launcher_executable must be "
                    "provided together",
                    {"side_effects_performed": False},
                )
            if int(launcher_pid or 0) <= 0 or int(launcher_hwnd or 0) <= 0:
                return OperationResult(
                    CapabilityState.UNAVAILABLE,
                    operation,
                    "launcher_pid and launcher_hwnd must be positive",
                    {"side_effects_performed": False},
                )
            executable = Path(launcher_executable).expanduser().resolve()
            if not executable.is_absolute() or not executable.is_file():
                return OperationResult(
                    CapabilityState.UNAVAILABLE,
                    operation,
                    "launcher_executable must be an existing absolute file",
                    {"side_effects_performed": False},
                )
        else:
            executable = None
        payload: Dict[str, Any] = {
            "expected_price": expected_price,
            "free_listing": True,
            "assets": [
                {
                    "asset_id": asset_id,
                    "expected_price": expected_price,
                    "free_listing": True,
                    "action": "add_to_library",
                }
                for asset_id in values
            ],
            "verification_required": (
                "re-read each asset's Epic/Fab ownership and local library evidence"
            ),
            "execution_contract": "one official Add to My Library action per asset",
        }
        if launcher_pid is not None:
            payload["launcher"] = {
                "pid": int(launcher_pid),
                "hwnd": int(launcher_hwnd or 0),
                "executable": str(executable),
            }
        return self._typed_hook_request(
            operation,
            hook_manifest,
            payload,
            confirmed=confirmed,
            dry_run=dry_run,
        )

    def fab_library_sync_request(
        self,
        launcher_pid: int,
        allowed_root: Union[str, Path],
        hook_manifest: Union[str, Path],
        *,
        database_paths: Optional[Sequence[Union[str, Path]]] = None,
        cache_roots: Optional[Sequence[Union[str, Path]]] = None,
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> OperationResult:
        """Refresh the local Fab index through a scoped user-owned hook."""

        operation = "fab.library_sync.request"
        if int(launcher_pid) <= 0:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                operation,
                "launcher_pid must be positive",
                {"side_effects_performed": False},
            )
        root = Path(allowed_root).expanduser().resolve()
        payload: Dict[str, Any] = {
            "launcher_pid": int(launcher_pid),
            "allowed_root": str(root),
            "verification_required": "re-read Fab library sources after the hook",
        }
        for field, values in (("database_paths", database_paths), ("cache_roots", cache_roots)):
            if values:
                scoped: list[str] = []
                for value in values:
                    try:
                        scoped.append(str(resolve_allowed_project(value, root)))
                    except ValueError as exc:
                        return OperationResult(
                            CapabilityState.UNAVAILABLE,
                            operation,
                            str(exc),
                            {"field": field, "side_effects_performed": False},
                        )
                payload[field] = scoped
        return self._typed_hook_request(
            operation,
            hook_manifest,
            payload,
            confirmed=confirmed,
            dry_run=dry_run,
            plan=OperationResult(
                CapabilityState.READ_ONLY,
                "fab.library_sync",
                "sync scope was validated; no local index mutation was performed by the adapter",
                {"launcher_pid": int(launcher_pid), "allowed_root": str(root)},
            ),
        )

    def fab_import_inventory_request(
        self,
        project_path: Union[str, Path],
        allowed_root: Union[str, Path],
        hook_manifest: Union[str, Path],
        *,
        destination_subdir: str = "Fab",
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> OperationResult:
        """Route a scoped project inventory read to a provider hook."""

        try:
            project = resolve_allowed_project(project_path, allowed_root)
            if Path(destination_subdir).is_absolute() or ".." in Path(destination_subdir).parts:
                raise ValueError("destination_subdir must be relative and cannot traverse")
            local = self.fab.project_import_inventory(
                project,
                allowed_root,
                destination_subdir=destination_subdir,
            )
        except ValueError as exc:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.import_inventory.request",
                str(exc),
                {"side_effects_performed": False},
            )
        payload = {
            "project_path": str(project),
            "allowed_root": str(Path(allowed_root).expanduser().resolve()),
            "destination_subdir": destination_subdir,
        }
        return self._typed_hook_request(
            "fab.import_inventory.request",
            hook_manifest,
            payload,
            confirmed=confirmed,
            dry_run=dry_run,
            plan=OperationResult(
                CapabilityState.READ_ONLY,
                "fab.import_inventory",
                "project import inventory was read before invoking the provider hook",
                local,
            ),
        )

    def fab_launcher_status_request(
        self,
        launcher_pid: int,
        hook_manifest: Union[str, Path],
        *,
        port: int = DEFAULT_FAB_STATUS_PORT,
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> OperationResult:
        """Route the Launcher Fab callback listener probe to a read-only hook."""

        try:
            local = probe_fab_status_listener(launcher_pid, port)
        except ValueError as exc:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.launcher_status.request",
                str(exc),
                {"side_effects_performed": False},
            )
        payload = {"launcher_pid": int(launcher_pid), "port": int(port)}
        return self._typed_hook_request(
            "fab.launcher_status.request",
            hook_manifest,
            payload,
            confirmed=confirmed,
            dry_run=dry_run,
            plan=OperationResult(
                CapabilityState.READ_ONLY,
                "fab.launcher_status",
                "Fab callback listener was probed before invoking the provider hook",
                local,
            ),
        )

    def fab_download_request(
        self,
        asset_id: str,
        project_path: Union[str, Path],
        allowed_root: Union[str, Path],
        hook_manifest: Union[str, Path],
        *,
        expected_price: Union[int, float] = 0,
        owned: bool = False,
        format: str = "unreal-engine",
        quality: str = "",
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> OperationResult:
        """Invoke a declared user-owned Fab download hook after policy checks."""

        plan = self.fab.plan_download(
            asset_id,
            project_path,
            allowed_root,
            expected_price,
            owned,
        )
        if expected_price != 0 or not owned:
            return plan
        if not isinstance(format, str) or format not in {
            "unreal-engine",
            "fbx",
            "glb",
            "gltf",
            "obj",
            "usd",
            "usdz",
            "texture-set",
        }:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.download",
                "unsupported Fab download format",
                {"asset_id": asset_id, "format": format, "side_effects_performed": False},
            )
        payload = {
            "asset_id": asset_id,
            "project_path": str(Path(project_path).expanduser().resolve()),
            "allowed_root": str(Path(allowed_root).expanduser().resolve()),
            "expected_price": expected_price,
            "owned": True,
            "format": format,
            "quality": quality,
        }
        hook_result = self.hook_invoke(
            hook_manifest,
            "fab.download.request",
            payload,
            confirmed=confirmed,
            dry_run=dry_run,
        )
        details = {
            "asset_id": asset_id,
            "project_path": payload["project_path"],
            "format": format,
            "quality": quality,
            "plan": plan.as_dict(),
            "hook": hook_result.as_dict(),
            "side_effects_performed": hook_result.details.get("side_effects_performed", False),
            "verification_required": (
                "re-read Epic's local Fab index and project import inventory after the hook"
            ),
        }
        return OperationResult(
            hook_result.state,
            "fab.download",
            "Fab download hook request processed; completion requires fresh evidence",
            details,
        )

    def fab_download_batch_request(
        self,
        asset_ids: Sequence[str],
        project_path: Union[str, Path],
        allowed_root: Union[str, Path],
        hook_manifest: Union[str, Path],
        *,
        expected_price: Union[int, float] = 0,
        owned: bool = False,
        format: str = "unreal-engine",
        quality: str = "",
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> OperationResult:
        """Dispatch a bounded batch of free, owned Fab downloads to a hook."""

        try:
            project = resolve_allowed_project(project_path, allowed_root)
            require_free_asset(expected_price, owned)
        except ValueError as exc:
            return OperationResult(
                CapabilityState.HUMAN_REQUIRED,
                "fab.download_batch.request",
                str(exc),
                {"side_effects_performed": False},
            )
        values = [str(item).strip() for item in asset_ids if str(item).strip()]
        if not values:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.download_batch.request",
                "asset_ids must contain at least one non-empty id",
                {"side_effects_performed": False},
            )
        if len(values) > 100:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.download_batch.request",
                "asset_ids is limited to 100 entries per request",
                {"count": len(values), "side_effects_performed": False},
            )
        if len(set(values)) != len(values):
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.download_batch.request",
                "asset_ids must not contain duplicates",
                {"side_effects_performed": False},
            )
        if format == "unreal-engine":
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.download_batch.request",
                "Fab Launcher does not batch-download UE native content; use add_to_project",
                {
                    "format": format,
                    "next_operation": (
                        "fab.add_to_project.request"
                        if len(values) == 1
                        else "fab.add_to_project_batch.request"
                    ),
                    "asset_count": len(values),
                    "side_effects_performed": False,
                },
            )
        allowed_formats = {
            "fbx",
            "glb",
            "gltf",
            "obj",
            "usd",
            "usdz",
            "texture-set",
        }
        if format not in allowed_formats:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.download_batch.request",
                "unsupported Fab download format",
                {"format": format, "side_effects_performed": False},
            )
        payload = {
            "project_path": str(project),
            "allowed_root": str(Path(allowed_root).expanduser().resolve()),
            "assets": [
                {
                    "asset_id": asset_id,
                    "expected_price": expected_price,
                    "owned": True,
                    "format": format,
                    "quality": quality,
                }
                for asset_id in values
            ],
            "verification_required": (
                "re-read each asset's Fab download status and project inventory"
            ),
        }
        return self._typed_hook_request(
            "fab.download_batch.request",
            hook_manifest,
            payload,
            confirmed=confirmed,
            dry_run=dry_run,
        )

    def fab_add_to_project_request(
        self,
        asset_id: str,
        project_path: Union[str, Path],
        allowed_root: Union[str, Path],
        hook_manifest: Union[str, Path],
        *,
        expected_price: Union[int, float] = 0,
        owned: bool = False,
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> OperationResult:
        """Dispatch the official UE-native Fab Add to Project operation."""

        try:
            project = resolve_allowed_project(project_path, allowed_root)
        except ValueError as exc:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.add_to_project.request",
                str(exc),
                {"asset_id": asset_id, "side_effects_performed": False},
            )
        try:
            require_free_asset(expected_price, owned)
        except ValueError as exc:
            return OperationResult(
                CapabilityState.HUMAN_REQUIRED,
                "fab.add_to_project.request",
                str(exc),
                {"asset_id": asset_id, "side_effects_performed": False},
            )
        if not isinstance(asset_id, str) or not asset_id.strip():
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.add_to_project.request",
                "asset_id must not be empty",
                {"project_path": str(project), "side_effects_performed": False},
            )
        payload = {
            "asset_id": asset_id.strip(),
            "project_path": str(project),
            "allowed_root": str(Path(allowed_root).expanduser().resolve()),
            "expected_price": expected_price,
            "owned": True,
            "format": "unreal-engine",
            "action": "add_to_project",
            "verification_required": (
                "re-read the Fab download status and Unreal project import inventory"
            ),
        }
        return self._typed_hook_request(
            "fab.add_to_project.request",
            hook_manifest,
            payload,
            confirmed=confirmed,
            dry_run=dry_run,
        )

    def fab_add_to_project_batch_request(
        self,
        asset_ids: Sequence[str],
        project_path: Union[str, Path],
        allowed_root: Union[str, Path],
        hook_manifest: Union[str, Path],
        *,
        expected_price: Union[int, float] = 0,
        owned: bool = False,
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> OperationResult:
        """Dispatch one official Add to Project action per UE-native asset.

        Fab does not expose a native batch Add to Project API.  The declared
        hook is therefore responsible for iterating these bounded entries and
        reporting per-asset completion; this adapter only validates the scope
        and free/owned policy.
        """

        try:
            project = resolve_allowed_project(project_path, allowed_root)
            require_free_asset(expected_price, owned)
        except ValueError as exc:
            return OperationResult(
                CapabilityState.HUMAN_REQUIRED,
                "fab.add_to_project_batch.request",
                str(exc),
                {"side_effects_performed": False},
            )
        values = [str(item).strip() for item in asset_ids if str(item).strip()]
        if not values:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.add_to_project_batch.request",
                "asset_ids must contain at least one non-empty id",
                {"side_effects_performed": False},
            )
        if len(values) > 100:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.add_to_project_batch.request",
                "asset_ids is limited to 100 entries per request",
                {"count": len(values), "side_effects_performed": False},
            )
        if len(set(values)) != len(values):
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.add_to_project_batch.request",
                "asset_ids must not contain duplicates",
                {"side_effects_performed": False},
            )
        payload = {
            "project_path": str(project),
            "allowed_root": str(Path(allowed_root).expanduser().resolve()),
            "assets": [
                {
                    "asset_id": asset_id,
                    "expected_price": expected_price,
                    "owned": True,
                    "format": "unreal-engine",
                    "action": "add_to_project",
                }
                for asset_id in values
            ],
            "verification_required": (
                "re-read each asset's Fab download status and Unreal project import inventory"
            ),
            "execution_contract": "one official Add to Project action per asset",
        }
        return self._typed_hook_request(
            "fab.add_to_project_batch.request",
            hook_manifest,
            payload,
            confirmed=confirmed,
            dry_run=dry_run,
        )

    def fab_export_request(
        self,
        asset_id: str,
        destination: Union[str, Path],
        allowed_root: Union[str, Path],
        hook_manifest: Union[str, Path],
        *,
        expected_price: Union[int, float] = 0,
        owned: bool = False,
        format: str = "unreal-engine",
        database_path: Optional[Union[str, Path]] = None,
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> OperationResult:
        """Dispatch a policy-checked export to a user-owned hook."""

        try:
            target = resolve_allowed_project(destination, allowed_root)
            require_free_asset(expected_price, owned)
        except ValueError as exc:
            return OperationResult(
                CapabilityState.HUMAN_REQUIRED,
                "fab.export.request",
                str(exc),
                {"asset_id": asset_id, "side_effects_performed": False},
            )
        allowed_formats = {
            "unreal-engine",
            "fbx",
            "glb",
            "gltf",
            "obj",
            "usd",
            "usdz",
            "texture-set",
        }
        if format not in allowed_formats:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.export.request",
                "unsupported Fab export format",
                {"asset_id": asset_id, "format": format, "side_effects_performed": False},
            )
        payload: Dict[str, Any] = {
            "asset_id": str(asset_id),
            "destination": str(target),
            "allowed_root": str(Path(allowed_root).expanduser().resolve()),
            "expected_price": expected_price,
            "owned": True,
            "format": format,
        }
        if database_path is not None:
            payload["database_path"] = str(Path(database_path).expanduser().resolve())
        return self._typed_hook_request(
            "fab.export.request",
            hook_manifest,
            payload,
            confirmed=confirmed,
            dry_run=dry_run,
        )

    def fab_import_cached_request(
        self,
        asset_id: str,
        project_path: Union[str, Path],
        allowed_root: Union[str, Path],
        hook_manifest: Union[str, Path],
        *,
        database_path: Optional[Union[str, Path]] = None,
        cache_roots: Optional[Sequence[Union[str, Path]]] = None,
        destination_subdir: str = "Fab",
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> OperationResult:
        """Dispatch one cached import to a declared importer hook."""

        try:
            project = resolve_allowed_project(project_path, allowed_root)
        except ValueError as exc:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.import_cached.request",
                str(exc),
                {"asset_id": asset_id, "side_effects_performed": False},
            )
        if Path(destination_subdir).is_absolute() or ".." in Path(destination_subdir).parts:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.import_cached.request",
                "destination_subdir must be relative and cannot traverse",
                {"asset_id": asset_id, "side_effects_performed": False},
            )
        payload: Dict[str, Any] = {
            "asset_id": str(asset_id),
            "project_path": str(project),
            "allowed_root": str(Path(allowed_root).expanduser().resolve()),
            "destination_subdir": destination_subdir,
        }
        if database_path is not None:
            payload["database_path"] = str(Path(database_path).expanduser().resolve())
        if cache_roots:
            payload["cache_roots"] = [
                str(Path(item).expanduser().resolve()) for item in cache_roots
            ]
        return self._typed_hook_request(
            "fab.import_cached.request",
            hook_manifest,
            payload,
            confirmed=confirmed,
            dry_run=dry_run,
        )

    def fab_import_all_cached_request(
        self,
        project_path: Union[str, Path],
        allowed_root: Union[str, Path],
        hook_manifest: Union[str, Path],
        *,
        database_paths: Optional[Sequence[Union[str, Path]]] = None,
        cache_roots: Optional[Sequence[Union[str, Path]]] = None,
        destination_subdir: str = "Fab",
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> OperationResult:
        """Dispatch a batch cached import to a declared importer hook."""

        try:
            project = resolve_allowed_project(project_path, allowed_root)
        except ValueError as exc:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.import_all_cached.request",
                str(exc),
                {"side_effects_performed": False},
            )
        if Path(destination_subdir).is_absolute() or ".." in Path(destination_subdir).parts:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "fab.import_all_cached.request",
                "destination_subdir must be relative and cannot traverse",
                {"side_effects_performed": False},
            )
        payload: Dict[str, Any] = {
            "project_path": str(project),
            "allowed_root": str(Path(allowed_root).expanduser().resolve()),
            "destination_subdir": destination_subdir,
        }
        if database_paths:
            payload["database_paths"] = [
                str(Path(item).expanduser().resolve()) for item in database_paths
            ]
        if cache_roots:
            payload["cache_roots"] = [
                str(Path(item).expanduser().resolve()) for item in cache_roots
            ]
        return self._typed_hook_request(
            "fab.import_all_cached.request",
            hook_manifest,
            payload,
            confirmed=confirmed,
            dry_run=dry_run,
        )

    def project_import_request(
        self,
        project_path: Union[str, Path],
        source: Union[str, Path],
        allowed_root: Union[str, Path],
        hook_manifest: Union[str, Path],
        *,
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> OperationResult:
        """Dispatch a project-scoped import while constraining both paths."""

        try:
            project = resolve_allowed_project(project_path, allowed_root)
            source_path = resolve_allowed_project(source, allowed_root)
        except ValueError as exc:
            return OperationResult(
                CapabilityState.UNAVAILABLE,
                "project.import.request",
                str(exc),
                {"side_effects_performed": False},
            )
        payload = {
            "project_path": str(project),
            "source": str(source_path),
            "allowed_root": str(Path(allowed_root).expanduser().resolve()),
        }
        return self._typed_hook_request(
            "project.import.request",
            hook_manifest,
            payload,
            confirmed=confirmed,
            dry_run=dry_run,
        )
