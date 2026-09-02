from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Union

from .hooks import HOOK_OPERATIONS, invoke_hook, load_hook_manifest, probe_hook
from .models import CapabilityState, LauncherBinding, OperationResult
from .providers.epic_launcher.manifest import DEFAULT_MANIFEST_ROOT, list_engine_installs
from .providers.epic_launcher.runtime import bind_launcher
from .providers.fab.service import FabService
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
            "fab": self.fab.capabilities(),
            "project.verify": CapabilityState.READ_ONLY.value,
            "hooks": {
                "probe": CapabilityState.READ_ONLY.value,
                "invoke": "available_if_declared",
                "protocol": "epic.hook.v1",
                "operations": sorted(HOOK_OPERATIONS),
            },
            "cua_fallback": False,
        }

    def launcher_status(self, binding: LauncherBinding) -> Dict[str, Any]:
        return bind_launcher(binding).status()

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
            editor = (
                entry.install_location
                / "Engine"
                / "Binaries"
                / "Win64"
                / "UnrealEditor.exe"
            )
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
