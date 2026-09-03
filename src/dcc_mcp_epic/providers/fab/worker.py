"""Small, protocol-safe Fab provider worker.

The adapter deliberately keeps Epic account ownership and downloads outside of
its process.  This module is the executable side of the ``epic.hook.v1``
bridge: it can provide real local, read-only evidence and can delegate account
mutations to an explicitly configured user-owned provider.  Without that
provider it returns a typed capability-unavailable result instead of claiming
that a Fab listing was acquired or downloaded.

The worker is intentionally language neutral.  A Python/Rust/other provider
can implement the same stdin/stdout contract; no C++/C# reflection or private
Epic Launcher memory hooks are required.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ...hooks import (
    HOOK_OPERATION_REQUIRED_FIELDS,
    HOOK_PROTOCOL,
    MUTATING_HOOK_OPERATIONS,
)
from ...models import CapabilityState
from .bridge import probe_fab_status_listener
from .service import DEFAULT_FAB_LIBRARY_DB, FabService

WORKER_VERSION = "0.1.0"
CATALOG_ENV = "DCC_MCP_EPIC_FAB_CATALOG_JSON"
PROVIDER_COMMAND_ENV = "DCC_MCP_EPIC_FAB_PROVIDER_COMMAND"
PROVIDER_TIMEOUT_ENV = "DCC_MCP_EPIC_FAB_PROVIDER_TIMEOUT"

# This is a Fab-only worker.  Keeping the allowlist narrow prevents an
# accidentally reused manifest from becoming an Engine or arbitrary Launcher
# command bridge.
SUPPORTED_OPERATIONS = frozenset(
    {
        "fab.search.request",
        "fab.catalog_free.request",
        "fab.asset_detail.request",
        "fab.library.request",
        "fab.library_sources.request",
        "fab.library_sync.request",
        "fab.free_assets_sync.request",
        "fab.download.request",
        "fab.download_batch.request",
        "fab.add_to_library.request",
        "fab.add_to_library_batch.request",
        "fab.add_to_project.request",
        "fab.add_to_project_batch.request",
        "fab.download_status.request",
        "fab.download_status_batch.request",
        "fab.export.request",
        "fab.import_cached.request",
        "fab.import_all_cached.request",
        "fab.import_inventory.request",
        "fab.launcher_import.request",
        "fab.launcher_status.request",
    }
)

READ_ONLY_OPERATIONS = frozenset(SUPPORTED_OPERATIONS - MUTATING_HOOK_OPERATIONS)


def _result(
    operation: str,
    state: CapabilityState,
    message: str,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    value = dict(details or {})
    value.setdefault("side_effects_performed", False)
    if operation not in MUTATING_HOOK_OPERATIONS or state is not CapabilityState.AVAILABLE:
        value["side_effects_performed"] = False
    return {
        "protocol": HOOK_PROTOCOL,
        "worker": "dcc-mcp-epic-fab-worker",
        "worker_version": WORKER_VERSION,
        "operation": operation,
        "state": state.value,
        "message": message,
        "details": value,
    }


def _path_list(payload: Dict[str, Any], key: str) -> Optional[List[str]]:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, (str, bytes)) or not isinstance(value, list):
        raise ValueError(f"{key} must be a list of paths")
    result: List[str] = []
    seen = set()
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{key} must contain non-empty path strings")
        resolved = str(Path(item).expanduser().resolve())
        marker = resolved.casefold()
        if marker not in seen:
            result.append(resolved)
            seen.add(marker)
    return result


class FabWorker:
    """Handle one JSON request without UI automation or credential access."""

    def __init__(self, *, provider_command: Optional[Sequence[str]] = None) -> None:
        self.fab = FabService()
        self._provider_command = tuple(provider_command) if provider_command else None

    @staticmethod
    def _configured_provider() -> Tuple[Optional[Tuple[str, ...]], Optional[str]]:
        raw = os.environ.get(PROVIDER_COMMAND_ENV, "").strip()
        if not raw:
            return None, None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            return None, f"{PROVIDER_COMMAND_ENV} must be a JSON array: {exc}"
        if (
            not isinstance(parsed, list)
            or not parsed
            or not all(isinstance(item, str) and item for item in parsed)
        ):
            return None, f"{PROVIDER_COMMAND_ENV} must be a non-empty JSON array of strings"
        executable = Path(parsed[0]).expanduser()
        if not executable.is_absolute() or not executable.is_file():
            return None, f"provider executable must be an existing absolute file: {parsed[0]}"
        return tuple(parsed), None

    @staticmethod
    def _provider_timeout() -> int:
        raw = os.environ.get(PROVIDER_TIMEOUT_ENV, "120")
        try:
            timeout = int(raw)
        except ValueError:
            return 120
        return max(1, min(timeout, 300))

    def _delegate(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        command = self._provider_command
        error = None
        if command is None:
            command, error = self._configured_provider()
        if error:
            return _result(
                str(request.get("operation") or "unknown"),
                CapabilityState.UNAVAILABLE,
                "configured Fab provider is invalid",
                {"code": "invalid_provider_configuration", "reason": error},
            )
        if not command:
            return None
        operation = str(request.get("operation") or "unknown")
        try:
            completed = subprocess.run(
                [*command, "--protocol", HOOK_PROTOCOL, "--operation", operation],
                input=json.dumps(request, ensure_ascii=False),
                capture_output=True,
                text=True,
                timeout=self._provider_timeout(),
                check=False,
                shell=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return _result(
                operation,
                CapabilityState.UNAVAILABLE,
                "configured Fab provider could not be started",
                {"code": "provider_process_failed", "reason": str(exc)},
            )
        if completed.returncode != 0:
            return _result(
                operation,
                CapabilityState.UNAVAILABLE,
                "configured Fab provider returned a non-zero exit code",
                {
                    "code": "provider_nonzero_exit",
                    "returncode": completed.returncode,
                    "stderr": completed.stderr[-4096:],
                },
            )
        try:
            response = json.loads(completed.stdout)
        except (TypeError, json.JSONDecodeError):
            return _result(
                operation,
                CapabilityState.UNAVAILABLE,
                "configured Fab provider returned invalid JSON",
                {"code": "provider_invalid_json"},
            )
        if not isinstance(response, dict):
            return _result(
                operation,
                CapabilityState.UNAVAILABLE,
                "configured Fab provider response must be a JSON object",
                {"code": "provider_invalid_response"},
            )
        if response.get("protocol") != HOOK_PROTOCOL or response.get("operation") != operation:
            return _result(
                operation,
                CapabilityState.UNAVAILABLE,
                "configured Fab provider returned a mismatched protocol response",
                {"code": "provider_protocol_mismatch"},
            )
        try:
            state = CapabilityState(str(response.get("state")))
        except ValueError:
            return _result(
                operation,
                CapabilityState.UNAVAILABLE,
                "configured Fab provider returned an unsupported capability state",
                {"code": "provider_invalid_state"},
            )
        details = response.get("details")
        if not isinstance(details, dict):
            details = {}
        details = dict(details)
        details.setdefault("provider_delegated", True)
        return _result(
            operation, state, str(response.get("message") or "provider completed"), details
        )

    @staticmethod
    def _catalog_asset(item: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(item, dict):
            return None
        asset_id = item.get("asset_id", item.get("uid", item.get("id")))
        title = item.get("title")
        price = item.get("price", item.get("current_price"))
        formats = item.get("formats", [])
        if not isinstance(asset_id, str) or not asset_id.strip():
            return None
        if not isinstance(title, str) or not title.strip():
            return None
        if isinstance(price, bool) or not isinstance(price, (int, float)) or float(price) != 0:
            return None
        if item.get("free_listing") is not True:
            return None
        if not isinstance(formats, list) or not all(isinstance(value, str) for value in formats):
            return None
        return {
            **item,
            "asset_id": asset_id.strip(),
            "title": title.strip(),
            "price": 0,
            "free_listing": True,
            "formats": sorted({value.strip() for value in formats if value.strip()}),
        }

    def _catalog_from_snapshot(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        path_value = os.environ.get(CATALOG_ENV, "").strip()
        if not path_value:
            return _result(
                "fab.catalog_free.request",
                CapabilityState.UNAVAILABLE,
                "no official Fab catalog provider is configured",
                {
                    "code": "official_provider_not_configured",
                    "provider_route": "official_fab_or_native_hook",
                    "next_action": f"configure {PROVIDER_COMMAND_ENV} or {CATALOG_ENV}",
                },
            )
        path = Path(path_value).expanduser().resolve()
        try:
            document = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            return _result(
                "fab.catalog_free.request",
                CapabilityState.UNAVAILABLE,
                "configured Fab catalog snapshot could not be read",
                {"code": "catalog_snapshot_unreadable", "path": str(path), "reason": str(exc)},
            )
        raw_assets: Any = document.get("assets") if isinstance(document, dict) else document
        if not isinstance(raw_assets, list):
            return _result(
                "fab.catalog_free.request",
                CapabilityState.UNAVAILABLE,
                "Fab catalog snapshot must contain an assets array",
                {"code": "catalog_snapshot_invalid", "path": str(path)},
            )
        assets = [asset for item in raw_assets if (asset := self._catalog_asset(item)) is not None]
        query = str(payload.get("query") or "").strip().casefold()
        categories = {str(value).strip().casefold() for value in payload.get("categories", [])}
        formats = {str(value).strip().casefold() for value in payload.get("formats", [])}
        filtered = []
        for asset in assets:
            haystack = f"{asset['asset_id']} {asset['title']}".casefold()
            if query and query not in haystack:
                continue
            category = str(asset.get("category", asset.get("category_name", ""))).casefold()
            if categories and category not in categories:
                continue
            asset_formats = {str(value).casefold() for value in asset.get("formats", [])}
            if formats and not formats.intersection(asset_formats):
                continue
            filtered.append(asset)
        try:
            limit = int(payload.get("limit", 100))
            offset = int(str(payload.get("cursor") or "0"))
        except (TypeError, ValueError):
            return _result(
                "fab.catalog_free.request",
                CapabilityState.UNAVAILABLE,
                "catalog limit/cursor is invalid",
                {"code": "catalog_paging_invalid"},
            )
        if limit < 1 or limit > 100 or offset < 0:
            return _result(
                "fab.catalog_free.request",
                CapabilityState.UNAVAILABLE,
                "catalog limit/cursor is outside the supported range",
                {"code": "catalog_paging_invalid"},
            )
        page = filtered[offset : offset + limit]
        next_cursor = str(offset + limit) if offset + limit < len(filtered) else ""
        return _result(
            "fab.catalog_free.request",
            CapabilityState.READ_ONLY,
            "free Fab catalog snapshot read",
            {
                "catalog_path": str(path),
                "provider_route": "configured_catalog_snapshot",
                "free_only": True,
                "query": payload.get("query", ""),
                "assets": page,
                "asset_count": len(page),
                "total_count": len(filtered),
                "next_cursor": next_cursor,
                "freshness": "caller-supplied snapshot; not an account mutation",
            },
        )

    def _local_read(self, operation: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if operation == "fab.catalog_free.request":
            return self._catalog_from_snapshot(payload)
        if operation == "fab.library.request":
            path = payload.get("database_path", DEFAULT_FAB_LIBRARY_DB)
            return _result(
                operation,
                CapabilityState.READ_ONLY,
                "local Fab library index read",
                self.fab.list_local_library(path),
            )
        if operation == "fab.library_sources.request":
            paths = _path_list(payload, "database_paths")
            roots = _path_list(payload, "search_roots")
            return _result(
                operation,
                CapabilityState.READ_ONLY,
                "local Fab library sources read",
                self.fab.list_local_libraries(
                    paths, search_roots=roots, max_depth=int(payload.get("max_depth", 6))
                ),
            )
        if operation == "fab.search.request":
            return _result(
                operation,
                CapabilityState.READ_ONLY,
                "local Fab library search completed",
                self.fab.search_local_library(
                    str(payload.get("query") or ""),
                    _path_list(payload, "database_paths"),
                    search_roots=_path_list(payload, "search_roots"),
                    category=str(payload.get("category") or ""),
                    formats=payload.get("formats") or [],
                    owned_only=bool(payload.get("owned_only", False)),
                    downloaded_only=bool(payload.get("downloaded_only", False)),
                    max_depth=int(payload.get("max_depth", 6)),
                ),
            )
        if operation == "fab.download_status.request":
            return _result(
                operation,
                CapabilityState.READ_ONLY,
                "local Fab download status read",
                self.fab.inspect_download_state(
                    str(payload.get("asset_id") or ""),
                    payload.get("database_path", DEFAULT_FAB_LIBRARY_DB),
                    cache_roots=_path_list(payload, "cache_roots"),
                ),
            )
        if operation == "fab.download_status_batch.request":
            values = payload.get("assets", [])
            asset_ids = [item.get("asset_id") for item in values if isinstance(item, dict)]
            return _result(
                operation,
                CapabilityState.READ_ONLY,
                "local Fab download status batch read",
                self.fab.inspect_download_states(
                    asset_ids,
                    _path_list(payload, "database_paths"),
                    search_roots=_path_list(payload, "search_roots"),
                    cache_roots=_path_list(payload, "cache_roots"),
                    max_depth=int(payload.get("max_depth", 6)),
                ),
            )
        if operation == "fab.asset_detail.request":
            asset_id = str(payload.get("asset_id") or "")
            library = self.fab.list_local_libraries(
                _path_list(payload, "database_paths"),
                search_roots=_path_list(payload, "search_roots"),
                max_depth=int(payload.get("max_depth", 6)),
            )
            asset = next(
                (item for item in library.get("assets", []) if item.get("uid") == asset_id), None
            )
            status = None
            if asset:
                status = self.fab.inspect_download_state(
                    asset_id,
                    asset.get("database_path", DEFAULT_FAB_LIBRARY_DB),
                    cache_roots=_path_list(payload, "cache_roots"),
                )
            return _result(
                operation,
                CapabilityState.READ_ONLY,
                "local Fab asset detail read",
                {"asset": asset, "download_status": status},
            )
        if operation == "fab.import_inventory.request":
            return _result(
                operation,
                CapabilityState.READ_ONLY,
                "project Fab import inventory read",
                self.fab.project_import_inventory(
                    str(payload.get("project_path") or ""),
                    str(payload.get("allowed_root") or ""),
                    destination_subdir=str(payload.get("destination_subdir") or "Fab"),
                ),
            )
        if operation == "fab.launcher_status.request":
            try:
                evidence = probe_fab_status_listener(
                    int(payload.get("launcher_pid")), int(payload.get("port", 24563))
                )
            except (TypeError, ValueError, OSError) as exc:
                return _result(
                    operation,
                    CapabilityState.UNAVAILABLE,
                    "Fab callback listener probe failed",
                    {"reason": str(exc)},
                )
            return _result(
                operation, CapabilityState.READ_ONLY, "Fab callback listener probed", evidence
            )
        return _result(
            operation,
            CapabilityState.UNAVAILABLE,
            "no local implementation is available for this mutating operation",
            {
                "code": "official_provider_not_configured",
                "provider_route": "official_fab_or_native_hook",
                "next_action": f"configure {PROVIDER_COMMAND_ENV} with an official/native provider",
            },
        )

    def _already_satisfied_sync(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Return an idempotent completion when local evidence is sufficient.

        This is intentionally read-only: it never changes Epic's index and it
        never treats a missing/unowned item as downloaded.  A request with any
        unsatisfied item still goes through the configured account provider.
        """

        operation = "fab.free_assets_sync.request"
        items = payload.get("assets")
        if not isinstance(items, list) or not items:
            return _result(
                operation,
                CapabilityState.UNAVAILABLE,
                "assets must be a non-empty list",
                {"code": "invalid_assets"},
            )
        asset_ids = [item.get("asset_id") for item in items if isinstance(item, dict)]
        if len(asset_ids) != len(items) or not all(
            isinstance(item, str) and item for item in asset_ids
        ):
            return _result(
                operation,
                CapabilityState.UNAVAILABLE,
                "assets must contain asset_id strings",
                {"code": "invalid_assets"},
            )
        try:
            statuses = self.fab.inspect_download_states(
                asset_ids,
                _path_list(payload, "database_paths"),
                search_roots=_path_list(payload, "search_roots"),
                cache_roots=_path_list(payload, "cache_roots"),
                max_depth=int(payload.get("max_depth", 6)),
            )
        except (OSError, TypeError, ValueError, KeyError) as exc:
            return _result(
                operation,
                CapabilityState.UNAVAILABLE,
                "local Fab status read failed",
                {"code": "local_status_failed", "reason": str(exc)},
            )
        mode = str(payload.get("mode") or "")
        require_download = mode != "library_only"
        evidence = []
        all_satisfied = True
        for requested, status in zip(items, statuses.get("assets", [])):
            owned = bool(status.get("owned"))
            downloaded = bool(status.get("downloaded"))
            format_matches = not requested.get("format") or str(status.get("format") or "") == str(
                requested.get("format")
            )
            satisfied = owned and (not require_download or (downloaded and format_matches))
            all_satisfied = all_satisfied and satisfied
            evidence.append(
                {
                    "asset_id": requested.get("asset_id"),
                    "satisfied": satisfied,
                    "owned": owned,
                    "downloaded": downloaded,
                    "format": status.get("format"),
                    "state": status.get("state"),
                }
            )
        if not all_satisfied:
            return _result(
                operation,
                CapabilityState.UNAVAILABLE,
                "one or more requested assets still require an official provider",
                {"code": "assets_not_satisfied", "assets": evidence, "status": statuses},
            )
        project_evidence = None
        if mode == "library_download_and_project":
            project_path = payload.get("project_path")
            allowed_root = payload.get("allowed_root")
            if not isinstance(project_path, str) or not isinstance(allowed_root, str):
                return _result(
                    operation,
                    CapabilityState.UNAVAILABLE,
                    "project_path and allowed_root are required for project mode",
                    {"code": "project_scope_missing"},
                )
            project_evidence = self.fab.project_import_inventory(project_path, allowed_root)
            imported = {
                str(item.get("asset_id"))
                for item in project_evidence.get("assets", [])
                if item.get("valid")
            }
            for item in evidence:
                item["imported"] = item["asset_id"] in imported
                item["satisfied"] = item["satisfied"] and item["imported"]
            all_satisfied = all(item["satisfied"] for item in evidence)
        if not all_satisfied:
            return _result(
                operation,
                CapabilityState.UNAVAILABLE,
                "requested project imports are not fully verified",
                {
                    "code": "project_not_satisfied",
                    "assets": evidence,
                    "project_inventory": project_evidence,
                },
            )
        return _result(
            operation,
            CapabilityState.AVAILABLE,
            "requested Fab assets already satisfy the sync contract; no mutation was needed",
            {
                "already_satisfied": True,
                "mode": mode,
                "assets": evidence,
                "project_inventory": project_evidence,
                "provider_route": "local_readback_idempotent_noop",
                "cua_calls_expected": 0,
                "side_effects_performed": False,
            },
        )

    def handle(self, request: Any) -> Dict[str, Any]:
        if not isinstance(request, dict):
            return _result(
                "unknown",
                CapabilityState.UNAVAILABLE,
                "hook request must be a JSON object",
                {"code": "invalid_request"},
            )
        if request.get("protocol") != HOOK_PROTOCOL:
            return _result(
                "unknown",
                CapabilityState.UNAVAILABLE,
                "unsupported hook protocol",
                {"code": "unsupported_protocol"},
            )
        operation = request.get("operation")
        payload = request.get("payload")
        if not isinstance(operation, str) or operation not in SUPPORTED_OPERATIONS:
            return _result(
                str(operation or "unknown"),
                CapabilityState.UNAVAILABLE,
                "operation is not supported by the Fab worker",
                {"code": "operation_not_supported"},
            )
        if not isinstance(payload, dict):
            return _result(
                operation,
                CapabilityState.UNAVAILABLE,
                "hook payload must be a JSON object",
                {"code": "invalid_payload"},
            )
        missing = [
            field
            for field in HOOK_OPERATION_REQUIRED_FIELDS.get(operation, [])
            if field not in payload or payload[field] in (None, "", [])
        ]
        if missing:
            return _result(
                operation,
                CapabilityState.UNAVAILABLE,
                "hook payload is missing required fields",
                {"code": "missing_fields", "missing_fields": missing},
            )
        if operation in READ_ONLY_OPERATIONS:
            try:
                return self._local_read(operation, payload)
            except (OSError, TypeError, ValueError, KeyError) as exc:
                return _result(
                    operation,
                    CapabilityState.UNAVAILABLE,
                    "local Fab read failed",
                    {"code": "local_read_failed", "reason": str(exc)},
                )
        preflight = None
        if operation == "fab.free_assets_sync.request":
            preflight = self._already_satisfied_sync(payload)
            if preflight.get("state") == CapabilityState.AVAILABLE.value:
                return preflight
            preflight_code = preflight.get("details", {}).get("code")
            if preflight_code in {"invalid_assets", "project_scope_missing"}:
                return preflight
        delegated = self._delegate(request)
        if delegated is not None:
            return delegated
        details = {
            "code": "official_provider_not_configured",
            "provider_route": "official_fab_or_native_hook",
            "cua_calls_expected": 0,
            "next_action": (
                f"configure {PROVIDER_COMMAND_ENV} with a supported provider; "
                "login/CAPTCHA remains human-controlled"
            ),
        }
        if preflight is not None:
            details["preflight"] = preflight.get("details", {})
        return _result(
            operation,
            CapabilityState.UNAVAILABLE,
            "no official/native Fab provider is configured for account or download work",
            details,
        )


def manifest(
    *, python_executable: Optional[str] = None, timeout_seconds: int = 120
) -> Dict[str, Any]:
    """Return a ready-to-save manifest for this worker."""

    executable = str(Path(python_executable or sys.executable).expanduser().resolve())
    digest = __import__("hashlib").sha256(Path(executable).read_bytes()).hexdigest()
    operations = sorted(SUPPORTED_OPERATIONS)
    return {
        "protocol": HOOK_PROTOCOL,
        "name": "dcc-mcp-epic-fab-worker",
        "version": WORKER_VERSION,
        "command": [executable, "-m", "dcc_mcp_epic.providers.fab.worker"],
        "operations": operations,
        "requires_confirmation": sorted(set(operations) & MUTATING_HOOK_OPERATIONS),
        "sha256": digest,
        "timeout_seconds": max(1, min(int(timeout_seconds), 300)),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run the dcc-mcp-epic Fab hook worker")
    parser.add_argument("--protocol", default=HOOK_PROTOCOL)
    parser.add_argument("--operation", default=None)
    args = parser.parse_args(argv)
    try:
        request = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        print(
            json.dumps(
                _result(
                    "unknown",
                    CapabilityState.UNAVAILABLE,
                    "invalid JSON on stdin",
                    {"code": "invalid_json", "reason": str(exc)},
                ),
                ensure_ascii=False,
            )
        )
        return 0
    if args.protocol != HOOK_PROTOCOL:
        print(
            json.dumps(
                _result(
                    "unknown",
                    CapabilityState.UNAVAILABLE,
                    "unsupported hook protocol",
                    {"code": "unsupported_protocol"},
                ),
                ensure_ascii=False,
            )
        )
        return 0
    response = FabWorker().handle(request)
    print(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via subprocess
    raise SystemExit(main())
