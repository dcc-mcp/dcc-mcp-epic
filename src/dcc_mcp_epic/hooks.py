from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from .models import CapabilityState, OperationResult

HOOK_PROTOCOL = "epic.hook.v1"
HOOK_OPERATIONS = frozenset(
    {
        "launcher.status",
        "engine.install.request",
        "engine.update.request",
        "engine.download.request",
        "engine.verify.request",
        "engine.launch.request",
        "fab.search.request",
        "fab.library.request",
        "fab.library_sources.request",
        "fab.download.request",
        "fab.download_batch.request",
        "fab.add_to_project.request",
        "fab.add_to_project_batch.request",
        "fab.download_status.request",
        "fab.export.request",
        "fab.import_cached.request",
        "fab.import_all_cached.request",
        "fab.import_inventory.request",
        "fab.launcher_import.request",
        "fab.launcher_status.request",
        "project.import.request",
    }
)
MUTATING_HOOK_OPERATIONS = frozenset(
    {
        "engine.install.request",
        "engine.update.request",
        "engine.download.request",
        "engine.launch.request",
        "fab.download.request",
        "fab.download_batch.request",
        "fab.add_to_project.request",
        "fab.add_to_project_batch.request",
        "fab.export.request",
        "fab.import_cached.request",
        "fab.import_all_cached.request",
        "fab.launcher_import.request",
        "project.import.request",
    }
)

# Stable, machine-readable metadata for hook authors.  Keep this contract
# deliberately small: it describes routing and minimum identity fields, not
# private Epic APIs or credentials.
HOOK_OPERATION_REQUIRED_FIELDS = {
    "launcher.status": [],
    "engine.install.request": ["target_version"],
    "engine.update.request": ["target_version"],
    "engine.download.request": ["target_version"],
    "engine.verify.request": ["manifest_root"],
    "engine.launch.request": ["target_version", "project_path"],
    "fab.search.request": ["query"],
    "fab.library.request": [],
    "fab.library_sources.request": [],
    "fab.download.request": ["asset_id", "project_path", "format"],
    "fab.download_batch.request": ["assets", "project_path"],
    "fab.add_to_project.request": ["asset_id", "project_path"],
    "fab.add_to_project_batch.request": ["assets", "project_path"],
    "fab.download_status.request": ["asset_id"],
    "fab.export.request": ["asset_id", "destination", "format"],
    "fab.import_cached.request": ["asset_id", "project_path"],
    "fab.import_all_cached.request": ["project_path"],
    "fab.import_inventory.request": ["project_path"],
    "fab.launcher_import.request": ["editor_pid", "editor_hwnd", "project_path"],
    "fab.launcher_status.request": ["launcher_pid"],
    "project.import.request": ["project_path", "source"],
}


def hook_contract() -> Dict[str, Any]:
    """Return the versioned hook contract without reading or writing a file."""

    operations = []
    for operation in sorted(HOOK_OPERATIONS):
        operations.append(
            {
                "name": operation,
                "mutating": operation in MUTATING_HOOK_OPERATIONS,
                "required_fields": list(HOOK_OPERATION_REQUIRED_FIELDS.get(operation, [])),
                "confirmation_required_by_default": operation in MUTATING_HOOK_OPERATIONS,
            }
        )
    return {
        "protocol": HOOK_PROTOCOL,
        "read_only": True,
        "operations": operations,
        "mutating_operations": sorted(MUTATING_HOOK_OPERATIONS),
        "dry_run_default": True,
        "executable_digest": "optional_sha256_manifest_field",
    }


@dataclass(frozen=True)
class HookSpec:
    name: str
    version: str
    command: Tuple[str, ...]
    operations: Tuple[str, ...]
    sha256: Optional[str]
    timeout_seconds: int
    requires_confirmation: Tuple[str, ...]

    def as_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["command"] = list(self.command)
        value["operations"] = list(self.operations)
        value["requires_confirmation"] = list(self.requires_confirmation)
        return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_hook_manifest(path: Union[str, Path]) -> HookSpec:
    manifest_path = Path(path).expanduser().resolve()
    data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if data.get("protocol") != HOOK_PROTOCOL:
        raise ValueError(f"unsupported hook protocol: {data.get('protocol')!r}")
    name = str(data.get("name", "")).strip()
    version = str(data.get("version", "")).strip()
    command = data.get("command")
    operations = data.get("operations")
    if not name or not version or not isinstance(command, list) or not command:
        raise ValueError("hook manifest requires name, version, and non-empty command")
    if not all(isinstance(item, str) and item for item in command):
        raise ValueError("hook command must contain only non-empty strings")
    executable = Path(command[0]).expanduser()
    if not executable.is_absolute() or not executable.is_file():
        raise ValueError("hook command[0] must be an existing absolute executable path")
    if not isinstance(operations, list) or not operations:
        raise ValueError("hook operations must be a non-empty list")
    unknown = sorted(set(operations) - HOOK_OPERATIONS)
    if unknown:
        raise ValueError(f"hook operations are not allowlisted: {unknown}")
    confirmations = data.get("requires_confirmation", [])
    if not isinstance(confirmations, list) or not set(confirmations).issubset(set(operations)):
        raise ValueError("requires_confirmation must be a subset of operations")
    missing_confirmations = sorted(
        (set(operations) & MUTATING_HOOK_OPERATIONS) - set(confirmations)
    )
    if missing_confirmations:
        raise ValueError(
            "mutating hook operations must require confirmation: "
            f"{missing_confirmations}"
        )
    digest = data.get("sha256")
    if digest is not None:
        digest = str(digest).lower()
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("hook sha256 must be a 64-character hexadecimal digest")
    timeout = int(data.get("timeout_seconds", 30))
    if not 1 <= timeout <= 300:
        raise ValueError("hook timeout_seconds must be between 1 and 300")
    return HookSpec(
        name=name,
        version=version,
        command=tuple(command),
        operations=tuple(sorted(set(operations))),
        sha256=digest,
        timeout_seconds=timeout,
        requires_confirmation=tuple(sorted(set(confirmations))),
    )


def probe_hook(spec: HookSpec) -> Dict[str, Any]:
    executable = Path(spec.command[0]).resolve()
    actual = _sha256(executable)
    return {
        "protocol": HOOK_PROTOCOL,
        "name": spec.name,
        "version": spec.version,
        "command": list(spec.command),
        "operations": list(spec.operations),
        "requires_confirmation": list(spec.requires_confirmation),
        "executable": str(executable),
        "sha256": actual,
        "sha256_verified": spec.sha256 is not None and actual == spec.sha256,
        "sha256_required": spec.sha256 is not None,
    }


def invoke_hook(
    spec: HookSpec,
    operation: str,
    payload: Dict[str, Any],
    *,
    confirmed: bool = False,
    dry_run: bool = True,
) -> OperationResult:
    if operation not in spec.operations:
        return OperationResult(
            CapabilityState.UNAVAILABLE,
            operation,
            "operation is not declared by the hook",
            {"hook": spec.name, "declared_operations": list(spec.operations)},
        )
    if not isinstance(payload, dict):
        return OperationResult(
            CapabilityState.UNAVAILABLE,
            operation,
            "hook payload must be a JSON object",
            {"hook": spec.name, "side_effects_performed": False},
        )
    if operation in spec.requires_confirmation and not confirmed:
        return OperationResult(
            CapabilityState.HUMAN_REQUIRED,
            operation,
            "hook operation requires explicit confirmation",
            {"hook": spec.name, "dry_run": True, "side_effects_performed": False},
        )
    evidence = probe_hook(spec)
    if spec.sha256 is not None and not evidence["sha256_verified"]:
        return OperationResult(
            CapabilityState.UNAVAILABLE,
            operation,
            "hook executable digest does not match the manifest",
            evidence,
        )
    if dry_run:
        return OperationResult(
            CapabilityState.READ_ONLY,
            operation,
            "hook request validated; dry-run performed",
            {"hook": spec.name, "payload": payload, "side_effects_performed": False},
        )
    request = {"protocol": HOOK_PROTOCOL, "operation": operation, "payload": payload}
    try:
        completed = subprocess.run(
            [*spec.command, "--protocol", HOOK_PROTOCOL, "--operation", operation],
            input=json.dumps(request, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=spec.timeout_seconds,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return OperationResult(
            CapabilityState.UNAVAILABLE,
            operation,
            f"hook process failed: {exc}",
            {"hook": spec.name, "side_effects_performed": False},
        )
    if completed.returncode != 0:
        return OperationResult(
            CapabilityState.UNAVAILABLE,
            operation,
            "hook returned a non-zero exit code",
            {
                "hook": spec.name,
                "returncode": completed.returncode,
                "stderr": completed.stderr[-4096:],
                "side_effects_performed": False,
            },
        )
    try:
        response = json.loads(completed.stdout)
    except ValueError:
        return OperationResult(
            CapabilityState.UNAVAILABLE,
            operation,
            "hook returned invalid JSON",
            {"hook": spec.name, "side_effects_performed": False},
        )
    # The operation allowlist is also a side-effect contract.  A hook may
    # still perform its own internal bookkeeping, but read-only operations
    # must never be reported as adapter-side mutations.  This keeps callers'
    # completion gates honest and lets typed read-only requests share the same
    # bridge as mutating requests.
    side_effects_performed = operation in MUTATING_HOOK_OPERATIONS
    return OperationResult(
        CapabilityState.AVAILABLE,
        operation,
        "hook operation completed",
        {
            "hook": spec.name,
            "response": response,
            "side_effects_performed": side_effects_performed,
        },
    )
