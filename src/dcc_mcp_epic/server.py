from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover - exercised in a minimal Python 3.9 install
    FastMCP = None  # type: ignore[assignment,misc]

from .hooks import hook_contract
from .models import LauncherBinding
from .providers.epic_launcher.manifest import DEFAULT_MANIFEST_ROOT
from .providers.fab.bridge import (
    DEFAULT_FAB_LAUNCHER_PORT,
    DEFAULT_FAB_STATUS_PORT,
    probe_fab_launcher,
    probe_fab_status_listener,
    send_import_request,
)
from .runtime import runtime_doctor
from .services import EpicService

_service = EpicService()


def epic_capabilities() -> Dict[str, Any]:
    """Return the explicit capability boundary of this adapter."""

    return _service.capabilities()


def epic_runtime_doctor() -> Dict[str, Any]:
    """Report reusable DCC-MCP and standalone runtime options."""

    return runtime_doctor()


def epic_hook_contract() -> Dict[str, Any]:
    """Describe the versioned self-owned hook interface."""

    return hook_contract()


def epic_engine_list_installed(manifest_root: str = None) -> Dict[str, Any]:
    """Read installed Unreal Engine entries; never writes Epic manifests."""

    return _service.list_engines(manifest_root) if manifest_root else _service.list_engines()


def epic_engine_update_plan(
    target_version: str, manifest_root: Optional[str] = None
) -> Dict[str, Any]:
    """Create a no-side-effect update plan and report whether a bridge is available."""

    root = manifest_root or str(DEFAULT_MANIFEST_ROOT)
    return _service.engine_update_plan(target_version, root).as_dict()


def epic_engine_download_plan(
    target_version: str, manifest_root: Optional[str] = None
) -> Dict[str, Any]:
    """Create a no-side-effect engine download plan."""

    root = manifest_root or str(DEFAULT_MANIFEST_ROOT)
    return _service.engine_download_plan(target_version, root).as_dict()


def epic_engine_launch_plan(
    target_version: str,
    project_path: str,
    manifest_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a no-side-effect UE launch plan."""

    root = manifest_root or str(DEFAULT_MANIFEST_ROOT)
    return _service.engine_launch_plan(target_version, project_path, root).as_dict()


def epic_engine_verify(manifest_root: Optional[str] = None) -> Dict[str, Any]:
    """Verify UnrealEditor.exe exists for every manifest-listed UE install."""

    return _service.verify_engines(manifest_root or str(DEFAULT_MANIFEST_ROOT))


def epic_engine_install_request(
    target_version: str,
    hook_manifest: str,
    install_root: Optional[str] = None,
    allowed_root: Optional[str] = None,
    confirmed: bool = False,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Dispatch a user-owned engine install hook with scoped paths."""

    return _service.engine_install_request(
        target_version,
        hook_manifest,
        install_root=install_root,
        allowed_root=allowed_root,
        confirmed=confirmed,
        dry_run=dry_run,
    ).as_dict()


def epic_engine_update_request(
    target_version: str,
    hook_manifest: str,
    manifest_root: Optional[str] = None,
    confirmed: bool = False,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Dispatch a user-owned engine update hook after a read-only plan."""

    return _service.engine_update_request(
        target_version,
        hook_manifest,
        manifest_root=manifest_root or str(DEFAULT_MANIFEST_ROOT),
        confirmed=confirmed,
        dry_run=dry_run,
    ).as_dict()


def epic_engine_download_request(
    target_version: str,
    hook_manifest: str,
    install_root: Optional[str] = None,
    allowed_root: Optional[str] = None,
    manifest_root: Optional[str] = None,
    confirmed: bool = False,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Dispatch a user-owned engine download hook with scoped paths."""

    return _service.engine_download_request(
        target_version,
        hook_manifest,
        install_root=install_root,
        allowed_root=allowed_root,
        manifest_root=manifest_root or str(DEFAULT_MANIFEST_ROOT),
        confirmed=confirmed,
        dry_run=dry_run,
    ).as_dict()


def epic_engine_verify_request(
    hook_manifest: str,
    manifest_root: Optional[str] = None,
    confirmed: bool = False,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Dispatch a user-owned engine verification hook with local evidence."""

    return _service.engine_verify_request(
        hook_manifest,
        manifest_root=manifest_root or str(DEFAULT_MANIFEST_ROOT),
        confirmed=confirmed,
        dry_run=dry_run,
    ).as_dict()


def epic_engine_launch_request(
    target_version: str,
    project_path: str,
    allowed_root: str,
    hook_manifest: str,
    manifest_root: Optional[str] = None,
    confirmed: bool = False,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Dispatch a project-scoped user-owned engine launch hook."""

    return _service.engine_launch_request(
        target_version,
        project_path,
        allowed_root,
        hook_manifest,
        manifest_root=manifest_root or str(DEFAULT_MANIFEST_ROOT),
        confirmed=confirmed,
        dry_run=dry_run,
    ).as_dict()


def epic_fab_library_list(database_path: Optional[str] = None) -> Dict[str, Any]:
    """Read the local Fab library index in read-only mode."""

    return (
        _service.fab.list_local_library(database_path)
        if database_path
        else _service.fab.list_local_library()
    )


def epic_fab_library_sources(
    database_paths: Optional[List[str]] = None,
    search_roots: Optional[List[str]] = None,
    max_depth: int = 6,
) -> Dict[str, Any]:
    """Discover and merge caller-selected local Fab library indexes read-only."""

    return _service.fab.list_local_libraries(
        database_paths,
        search_roots=search_roots,
        max_depth=max_depth,
    )


def epic_fab_asset_inspect(asset_id: str, database_path: Optional[str] = None) -> Dict[str, Any]:
    """Inspect one local Fab asset without changing the cache."""

    return (
        _service.fab.inspect_local_asset(asset_id, database_path)
        if database_path
        else _service.fab.inspect_local_asset(asset_id)
    )


def epic_fab_search(
    query: str = "",
    database_paths: Optional[List[str]] = None,
    search_roots: Optional[List[str]] = None,
    category: str = "",
    formats: Optional[List[str]] = None,
    owned_only: bool = False,
    downloaded_only: bool = False,
    max_depth: int = 6,
) -> Dict[str, Any]:
    """Search all caller-selected local Fab indexes read-only."""

    return _service.fab.search_local_library(
        query,
        database_paths,
        search_roots=search_roots,
        category=category,
        formats=formats,
        owned_only=owned_only,
        downloaded_only=downloaded_only,
        max_depth=max_depth,
    )


def epic_fab_download_status(
    asset_id: str,
    database_path: Optional[str] = None,
    cache_roots: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Re-read local Fab state to verify a hook download landed in cache."""

    if database_path:
        return _service.fab.inspect_download_state(
            asset_id, database_path, cache_roots=cache_roots
        )
    return _service.fab.inspect_download_state(asset_id, cache_roots=cache_roots)


def epic_fab_download_plan(
    asset_id: str,
    project_path: str,
    allowed_root: str,
    expected_price: float = 0,
    owned: bool = False,
) -> Dict[str, Any]:
    """Validate a free Fab download request without automating login or purchase."""

    return _service.fab.plan_download(
        asset_id, project_path, allowed_root, expected_price, owned
    ).as_dict()


def epic_fab_download_request(
    asset_id: str,
    project_path: str,
    allowed_root: str,
    hook_manifest: str,
    expected_price: float = 0,
    owned: bool = False,
    format: str = "unreal-engine",
    quality: str = "",
    confirmed: bool = False,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Dispatch a policy-checked Fab download request to a user-owned hook."""

    return _service.fab_download_request(
        asset_id,
        project_path,
        allowed_root,
        hook_manifest,
        expected_price=expected_price,
        owned=owned,
        format=format,
        quality=quality,
        confirmed=confirmed,
        dry_run=dry_run,
    ).as_dict()


def epic_fab_export_request(
    asset_id: str,
    destination: str,
    allowed_root: str,
    hook_manifest: str,
    expected_price: float = 0,
    owned: bool = False,
    format: str = "unreal-engine",
    database_path: Optional[str] = None,
    confirmed: bool = False,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Dispatch a policy-checked Fab export to a user-owned hook."""

    return _service.fab_export_request(
        asset_id,
        destination,
        allowed_root,
        hook_manifest,
        expected_price=expected_price,
        owned=owned,
        format=format,
        database_path=database_path,
        confirmed=confirmed,
        dry_run=dry_run,
    ).as_dict()


def epic_fab_download_batch_request(
    asset_ids: List[str],
    project_path: str,
    allowed_root: str,
    hook_manifest: str,
    expected_price: float = 0,
    owned: bool = False,
    format: str = "unreal-engine",
    quality: str = "",
    confirmed: bool = False,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Dispatch a bounded batch of free Fab downloads to a user-owned hook."""

    return _service.fab_download_batch_request(
        asset_ids,
        project_path,
        allowed_root,
        hook_manifest,
        expected_price=expected_price,
        owned=owned,
        format=format,
        quality=quality,
        confirmed=confirmed,
        dry_run=dry_run,
    ).as_dict()


def epic_fab_add_to_project_request(
    asset_id: str,
    project_path: str,
    allowed_root: str,
    hook_manifest: str,
    expected_price: float = 0,
    owned: bool = False,
    confirmed: bool = False,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Dispatch the official UE-native Fab Add to Project flow to a hook."""

    return _service.fab_add_to_project_request(
        asset_id,
        project_path,
        allowed_root,
        hook_manifest,
        expected_price=expected_price,
        owned=owned,
        confirmed=confirmed,
        dry_run=dry_run,
    ).as_dict()


def epic_fab_add_to_project_batch_request(
    asset_ids: List[str],
    project_path: str,
    allowed_root: str,
    hook_manifest: str,
    expected_price: float = 0,
    owned: bool = False,
    confirmed: bool = False,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Dispatch bounded per-asset UE-native Fab Add to Project actions."""

    return _service.fab_add_to_project_batch_request(
        asset_ids,
        project_path,
        allowed_root,
        hook_manifest,
        expected_price=expected_price,
        owned=owned,
        confirmed=confirmed,
        dry_run=dry_run,
    ).as_dict()


def epic_fab_import_cached_request(
    asset_id: str,
    project_path: str,
    allowed_root: str,
    hook_manifest: str,
    database_path: Optional[str] = None,
    cache_roots: Optional[List[str]] = None,
    destination_subdir: str = "Fab",
    confirmed: bool = False,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Dispatch one cached Fab import to a user-owned hook."""

    return _service.fab_import_cached_request(
        asset_id,
        project_path,
        allowed_root,
        hook_manifest,
        database_path=database_path,
        cache_roots=cache_roots,
        destination_subdir=destination_subdir,
        confirmed=confirmed,
        dry_run=dry_run,
    ).as_dict()


def epic_fab_import_all_cached_request(
    project_path: str,
    allowed_root: str,
    hook_manifest: str,
    database_paths: Optional[List[str]] = None,
    cache_roots: Optional[List[str]] = None,
    destination_subdir: str = "Fab",
    confirmed: bool = False,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Dispatch a batch cached Fab import to a user-owned hook."""

    return _service.fab_import_all_cached_request(
        project_path,
        allowed_root,
        hook_manifest,
        database_paths=database_paths,
        cache_roots=cache_roots,
        destination_subdir=destination_subdir,
        confirmed=confirmed,
        dry_run=dry_run,
    ).as_dict()


def epic_fab_import_cached_asset(
    asset_id: str,
    project_path: str,
    allowed_root: str,
    database_path: Optional[str] = None,
    destination_subdir: str = "Fab",
    cache_roots: Optional[List[str]] = None,
    confirmed: bool = False,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Plan or import one already-owned, downloaded Fab asset into ``Content``."""

    kwargs = {
        "destination_subdir": destination_subdir,
        "cache_roots": cache_roots,
        "confirmed": confirmed,
        "dry_run": dry_run,
    }
    if database_path:
        kwargs["database_path"] = database_path
    return _service.fab.plan_import_cached_asset(
        asset_id, project_path, allowed_root, **kwargs
    ).as_dict()


def epic_fab_import_all_cached(
    project_path: str,
    allowed_root: str,
    database_path: Optional[str] = None,
    database_paths: Optional[List[str]] = None,
    cache_roots: Optional[List[str]] = None,
    confirmed: bool = False,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Plan or import every owned/downloaded local Fab Unreal asset."""

    if database_path:
        return _service.fab.import_all_cached_assets(
            project_path,
            allowed_root,
            database_path,
            database_paths=database_paths,
            cache_roots=cache_roots,
            confirmed=confirmed,
            dry_run=dry_run,
        )
    return _service.fab.import_all_cached_assets(
        project_path,
        allowed_root,
        database_paths=database_paths,
        cache_roots=cache_roots,
        confirmed=confirmed,
        dry_run=dry_run,
    )


def epic_fab_project_inventory(
    project_path: str,
    allowed_root: str,
    destination_subdir: str = "Fab",
) -> Dict[str, Any]:
    """Audit imported Fab manifests and file hashes in a UE project."""

    return _service.fab.project_import_inventory(
        project_path, allowed_root, destination_subdir=destination_subdir
    )


def epic_fab_launcher_probe(
    editor_pid: int, port: int = DEFAULT_FAB_LAUNCHER_PORT
) -> Dict[str, Any]:
    """Probe the UE FabLauncher TCP endpoint without sending data."""

    return probe_fab_launcher(editor_pid, port)


def epic_fab_launcher_status_probe(
    launcher_pid: int, port: int = DEFAULT_FAB_STATUS_PORT
) -> Dict[str, Any]:
    """Probe the Launcher callback listener used for Fab import status."""

    return probe_fab_status_listener(launcher_pid, port)


def epic_fab_launcher_import_request(
    payload: Dict[str, Any],
    editor_pid: int,
    editor_hwnd: int,
    editor_executable: str,
    project_path: str,
    allowed_root: str,
    port: int = DEFAULT_FAB_LAUNCHER_PORT,
    confirmed: bool = False,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Validate/send a payload to the exact bound UE FabLauncher process."""

    return send_import_request(
        payload,
        editor_pid=editor_pid,
        editor_hwnd=editor_hwnd,
        editor_executable=editor_executable,
        project_path=project_path,
        allowed_root=allowed_root,
        port=port,
        confirmed=confirmed,
        dry_run=dry_run,
    ).as_dict()


def epic_project_verify(project_path: str, expected_engine: str = "5.5") -> Dict[str, Any]:
    """Verify a UE project association and list declared plugins."""

    return _service.verify_project(project_path, expected_engine)


def epic_project_import_request(
    project_path: str,
    source: str,
    allowed_root: str,
    hook_manifest: str,
    confirmed: bool = False,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Dispatch a project-scoped import to a user-owned hook."""

    return _service.project_import_request(
        project_path,
        source,
        allowed_root,
        hook_manifest,
        confirmed=confirmed,
        dry_run=dry_run,
    ).as_dict()


def epic_launcher_status(pid: int, hwnd: int, executable: str, version: str) -> Dict[str, Any]:
    """Bind to one exact Launcher process/window and return read-only status."""

    binding = LauncherBinding(pid, hwnd, Path(executable), version)
    return _service.launcher_status(binding)


def epic_hook_probe(manifest_path: str) -> Dict[str, Any]:
    """Validate a user-owned epic.hook.v1 manifest and executable digest."""

    return _service.hook_probe(manifest_path)


def epic_hook_invoke(
    manifest_path: str,
    operation: str,
    payload: Dict[str, Any],
    confirmed: bool = False,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Invoke only a declared hook operation; dry-run is the default."""

    return _service.hook_invoke(
        manifest_path,
        operation,
        payload,
        confirmed=confirmed,
        dry_run=dry_run,
    ).as_dict()


if FastMCP is not None:
    mcp = FastMCP("dcc-mcp-epic")
    for _tool in (
        epic_capabilities,
        epic_runtime_doctor,
        epic_hook_contract,
        epic_engine_list_installed,
        epic_engine_update_plan,
        epic_engine_download_plan,
        epic_engine_launch_plan,
        epic_engine_verify,
        epic_engine_install_request,
        epic_engine_update_request,
        epic_engine_download_request,
        epic_engine_verify_request,
        epic_engine_launch_request,
        epic_fab_library_list,
        epic_fab_library_sources,
        epic_fab_asset_inspect,
        epic_fab_search,
        epic_fab_download_status,
        epic_fab_download_plan,
        epic_fab_download_request,
        epic_fab_download_batch_request,
        epic_fab_add_to_project_request,
        epic_fab_add_to_project_batch_request,
        epic_fab_export_request,
        epic_fab_import_cached_request,
        epic_fab_import_all_cached_request,
        epic_fab_import_cached_asset,
        epic_fab_import_all_cached,
        epic_fab_project_inventory,
        epic_fab_launcher_probe,
        epic_fab_launcher_status_probe,
        epic_fab_launcher_import_request,
        epic_project_verify,
        epic_project_import_request,
        epic_launcher_status,
        epic_hook_probe,
        epic_hook_invoke,
    ):
        mcp.tool()(_tool)
else:
    mcp = None


def main() -> None:
    if mcp is None:
        raise RuntimeError(
            "MCP SDK is not installed; install the optional 'mcp' extra on Python 3.10+"
        )
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
