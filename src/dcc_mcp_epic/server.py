from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover - exercised in a minimal Python 3.9 install
    FastMCP = None  # type: ignore[assignment,misc]

from .models import LauncherBinding
from .providers.epic_launcher.manifest import DEFAULT_MANIFEST_ROOT
from .runtime import runtime_doctor
from .services import EpicService

_service = EpicService()


def epic_capabilities() -> Dict[str, Any]:
    """Return the explicit capability boundary of this adapter."""

    return _service.capabilities()


def epic_runtime_doctor() -> Dict[str, Any]:
    """Report reusable DCC-MCP and standalone runtime options."""

    return runtime_doctor()


def epic_engine_list_installed(manifest_root: str = None) -> Dict[str, Any]:
    """Read installed Unreal Engine entries; never writes Epic manifests."""

    return _service.list_engines(manifest_root) if manifest_root else _service.list_engines()


def epic_engine_update_plan(
    target_version: str, manifest_root: Optional[str] = None
) -> Dict[str, Any]:
    """Create a no-side-effect update plan and report whether a bridge is available."""

    root = manifest_root or str(DEFAULT_MANIFEST_ROOT)
    return _service.engine_update_plan(target_version, root).as_dict()


def epic_engine_verify(manifest_root: Optional[str] = None) -> Dict[str, Any]:
    """Verify UnrealEditor.exe exists for every manifest-listed UE install."""

    return _service.verify_engines(manifest_root or str(DEFAULT_MANIFEST_ROOT))


def epic_fab_library_list(database_path: Optional[str] = None) -> Dict[str, Any]:
    """Read the local Fab library index in read-only mode."""

    return (
        _service.fab.list_local_library(database_path)
        if database_path
        else _service.fab.list_local_library()
    )


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


def epic_project_verify(project_path: str, expected_engine: str = "5.5") -> Dict[str, Any]:
    """Verify a UE project association and list declared plugins."""

    return _service.verify_project(project_path, expected_engine)


def epic_launcher_status(pid: int, hwnd: int, executable: str, version: str) -> Dict[str, Any]:
    """Bind to one exact Launcher process/window and return read-only status."""

    binding = LauncherBinding(pid, hwnd, Path(executable), version)
    return _service.launcher_status(binding)


if FastMCP is not None:
    mcp = FastMCP("dcc-mcp-epic")
    for _tool in (
        epic_capabilities,
        epic_runtime_doctor,
        epic_engine_list_installed,
        epic_engine_update_plan,
        epic_engine_verify,
        epic_fab_library_list,
        epic_fab_download_plan,
        epic_project_verify,
        epic_launcher_status,
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
