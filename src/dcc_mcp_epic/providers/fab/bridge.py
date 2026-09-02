from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Any, Dict, Iterable, Union

import psutil

from ...models import CapabilityState, OperationResult
from ...policy import resolve_allowed_project
from ..epic_launcher.runtime import _window_owner

DEFAULT_FAB_LAUNCHER_PORT = 23429
DEFAULT_FAB_STATUS_PORT = 24563
_PATH_FIELDS = ("path", "native_files", "additional_textures")
_IMPORT_EXTENSIONS = {".fbx", ".glb", ".gltf", ".obj", ".usd", ".usdz", ".abc", ".mhpkg"}


def _path_under(path: Union[str, Path], root: Path) -> Path:
    candidate = Path(path).expanduser().resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"payload path is outside allowed root: {candidate}") from exc
    return candidate


def _iter_payload_paths(asset: Dict[str, Any]) -> Iterable[str]:
    for field in _PATH_FIELDS:
        value = asset.get(field, [])
        values = [value] if field == "path" and isinstance(value, str) else value
        if not isinstance(values, list):
            raise ValueError(f"asset field {field!r} must be a string or list")
        for item in values:
            if not isinstance(item, str) or not item:
                raise ValueError(f"asset field {field!r} contains a non-string path")
            yield item
    meshes = asset.get("meshes", [])
    if not isinstance(meshes, list):
        raise ValueError("asset field 'meshes' must be a list")
    for mesh in meshes:
        if not isinstance(mesh, dict):
            raise ValueError("mesh entries must be JSON objects")
        for key in ("file",):
            if mesh.get(key):
                if not isinstance(mesh[key], str):
                    raise ValueError(f"mesh field {key!r} must be a string")
                yield mesh[key]
        lods = mesh.get("lods", [])
        if not isinstance(lods, list):
            raise ValueError("mesh field 'lods' must be a list")
        for lod in lods:
            if not isinstance(lod, dict) or not isinstance(lod.get("file"), str):
                raise ValueError("mesh LOD entries must contain a string file")
            yield lod["file"]
    materials = asset.get("materials", [])
    if not isinstance(materials, list):
        raise ValueError("asset field 'materials' must be a list")
    for material in materials:
        if not isinstance(material, dict):
            raise ValueError("material entries must be JSON objects")
        if material.get("file"):
            if not isinstance(material["file"], str):
                raise ValueError("material field 'file' must be a string")
            yield material["file"]
        textures = material.get("textures", {})
        if not isinstance(textures, dict):
            raise ValueError("material field 'textures' must be an object")
        for texture in textures.values():
            if not isinstance(texture, str) or not texture:
                raise ValueError("material textures must contain string paths")
            yield texture


def validate_import_payload(
    payload: Dict[str, Any], allowed_root: Union[str, Path]
) -> Dict[str, Any]:
    """Validate the documented FabLauncher JSON shape and all source files."""

    if not isinstance(payload, dict) or not isinstance(payload.get("assets"), list):
        raise ValueError("payload must be an object containing an assets list")
    assets = payload["assets"]
    if not assets:
        raise ValueError("assets list must not be empty")
    if len(assets) > 128:
        raise ValueError("assets list exceeds the 128-asset limit")
    root = Path(allowed_root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"allowed root does not exist: {root}")
    validated = []
    for asset in assets:
        if not isinstance(asset, dict):
            raise ValueError("asset entries must be JSON objects")
        asset_id = asset.get("id")
        if not isinstance(asset_id, str) or not asset_id.strip():
            raise ValueError("every asset requires a non-empty string id")
        paths = []
        for value in _iter_payload_paths(asset):
            resolved = _path_under(value, root)
            if not resolved.is_file() and not resolved.is_dir():
                raise ValueError(f"payload path does not exist: {resolved}")
            if resolved.is_file() and resolved.suffix.lower() not in _IMPORT_EXTENSIONS:
                raise ValueError(f"unsupported Fab import file extension: {resolved.suffix}")
            paths.append(str(resolved))
        if not paths:
            raise ValueError(f"asset {asset_id!r} has no import files")
        validated.append({"id": asset_id, "path_count": len(paths), "paths": paths})
    return {"assets": validated, "asset_count": len(validated), "root": str(root)}


def probe_fab_launcher(pid: int, port: int = DEFAULT_FAB_LAUNCHER_PORT) -> Dict[str, Any]:
    """Read-only probe for the UE FabLauncher TCP import endpoint."""

    if pid <= 0 or not 1 <= port <= 65535:
        raise ValueError("pid and port must be valid positive values")
    try:
        process = psutil.Process(pid)
        actual_executable = process.exe()
        connections = psutil.net_connections(kind="tcp")
    except psutil.Error as exc:
        return {
            "protocol": "fablauncher.tcp.v1",
            "pid": pid,
            "port": port,
            "listening": False,
            "error": str(exc),
        }
    listeners = []
    for connection in connections:
        if not connection.laddr or connection.laddr.port != port:
            continue
        if connection.status != psutil.CONN_LISTEN or connection.pid != pid:
            continue
        listeners.append(str(connection.laddr.ip))
    return {
        "protocol": "fablauncher.tcp.v1",
        "pid": pid,
        "port": port,
        "listening": bool(listeners),
        "addresses": sorted(set(listeners)),
        "actual_executable": actual_executable,
        "status_port": DEFAULT_FAB_STATUS_PORT,
        "read_only": True,
    }


def send_import_request(
    payload: Dict[str, Any],
    *,
    editor_pid: int,
    editor_hwnd: int,
    editor_executable: Union[str, Path],
    project_path: Union[str, Path],
    allowed_root: Union[str, Path],
    port: int = DEFAULT_FAB_LAUNCHER_PORT,
    confirmed: bool = False,
    dry_run: bool = True,
    timeout_seconds: float = 5.0,
) -> OperationResult:
    """Send an explicitly confirmed payload to the UE FabLauncher server."""

    operation = "fab.launcher_import"
    project = resolve_allowed_project(project_path, allowed_root)
    if project.suffix.lower() == ".uproject":
        project = project.parent
    try:
        evidence = validate_import_payload(payload, allowed_root)
    except ValueError as exc:
        return OperationResult(
            CapabilityState.UNAVAILABLE,
            operation,
            str(exc),
            {"side_effects_performed": False},
        )
    try:
        process = psutil.Process(editor_pid)
        if not process.is_running():
            raise ValueError(f"UnrealEditor process is not running: {editor_pid}")
        actual = Path(process.exe()).resolve()
        expected = Path(editor_executable).expanduser().resolve()
        if os.path.normcase(str(actual)) != os.path.normcase(str(expected)):
            raise ValueError(f"editor executable mismatch: expected {expected}, got {actual}")
        owner = _window_owner(editor_hwnd)
        if owner != editor_pid:
            raise ValueError(f"editor HWND {editor_hwnd} is not owned by PID {editor_pid}")
    except (OSError, psutil.Error, ValueError) as exc:
        return OperationResult(
            CapabilityState.UNAVAILABLE,
            operation,
            f"exact UnrealEditor binding failed: {exc}",
            {"editor_pid": editor_pid, "editor_hwnd": editor_hwnd, "side_effects_performed": False},
        )
    probe = probe_fab_launcher(editor_pid, port)
    details = {
        "editor_pid": editor_pid,
        "editor_hwnd": editor_hwnd,
        "editor_executable": str(actual),
        "project_path": str(project),
        "port": port,
        "payload": evidence,
        "status_port": DEFAULT_FAB_STATUS_PORT,
        "side_effects_performed": False,
    }
    if not probe.get("listening"):
        return OperationResult(
            CapabilityState.UNAVAILABLE,
            operation,
            "FabLauncher TCP server is not listening on the bound UnrealEditor PID",
            {**details, "probe": probe},
        )
    if dry_run:
        return OperationResult(
            CapabilityState.READ_ONLY,
            operation,
            "FabLauncher import request validated; dry-run performed",
            details,
        )
    if not confirmed:
        return OperationResult(
            CapabilityState.HUMAN_REQUIRED,
            operation,
            "FabLauncher import request requires explicit confirmation",
            details,
        )
    wire = json.dumps(payload["assets"], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout_seconds) as connection:
            connection.sendall(wire + b"\x00")
    except OSError as exc:
        return OperationResult(
            CapabilityState.UNAVAILABLE,
            operation,
            f"FabLauncher TCP request failed: {exc}",
            details,
        )
    details["side_effects_performed"] = True
    details["verification_required"] = (
        "wait for FabLauncher status callback and refresh the UE asset registry"
    )
    return OperationResult(
        CapabilityState.AVAILABLE,
        operation,
        "FabLauncher import payload delivered; completion requires fresh UE evidence",
        details,
    )
