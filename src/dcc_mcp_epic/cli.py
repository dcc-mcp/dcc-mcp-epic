from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Optional

from .models import LauncherBinding
from .providers.epic_launcher.manifest import DEFAULT_MANIFEST_ROOT
from .providers.fab.bridge import (
    DEFAULT_FAB_LAUNCHER_PORT,
    DEFAULT_FAB_STATUS_PORT,
    probe_fab_launcher,
    probe_fab_status_listener,
    send_import_request,
)
from .providers.fab.service import DEFAULT_FAB_LIBRARY_DB
from .runtime import runtime_doctor
from .services import EpicService


def _dump(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Typed Epic Launcher/Fab adapter diagnostics")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("capabilities")
    sub.add_parser("runtime-doctor")
    sub.add_parser("hook-contract")
    engines = sub.add_parser("engines")
    engines.add_argument("--manifest-root", default=None)
    engine_verify = sub.add_parser("engine-verify")
    engine_verify.add_argument("--manifest-root", default=None)
    fab_library = sub.add_parser("fab-library")
    fab_library.add_argument("--database", default=None)
    fab_sources = sub.add_parser("fab-library-sources")
    fab_sources.add_argument(
        "--database", dest="databases", action="append", default=None,
        help="Explicit listings_v1.db path; repeat for multiple Epic cache indexes",
    )
    fab_sources.add_argument(
        "--search-root", dest="search_roots", action="append", default=None,
        help="Root to scan read-only for listings_v1.db; repeat as needed",
    )
    fab_sources.add_argument("--max-depth", type=int, default=6)
    project = sub.add_parser("project-verify")
    project.add_argument("project_path")
    project.add_argument("--engine", default="5.5")
    project_import = sub.add_parser("project-import-request")
    project_import.add_argument("project_path")
    project_import.add_argument("source")
    project_import.add_argument("--allowed-root", required=True)
    project_import.add_argument("--hook-manifest", required=True)
    project_import.add_argument("--confirmed", action="store_true")
    project_import.add_argument("--execute", action="store_true")
    plan = sub.add_parser("engine-update-plan")
    plan.add_argument("target_version")
    plan.add_argument("--manifest-root", default=None)
    download = sub.add_parser("engine-download-plan")
    download.add_argument("target_version")
    download.add_argument("--manifest-root", default=None)
    launch = sub.add_parser("engine-launch-plan")
    launch.add_argument("target_version")
    launch.add_argument("project_path")
    launch.add_argument("--manifest-root", default=None)
    engine_install = sub.add_parser("engine-install-request")
    engine_install.add_argument("target_version")
    engine_install.add_argument("--hook-manifest", required=True)
    engine_install.add_argument("--install-root", default=None)
    engine_install.add_argument("--allowed-root", default=None)
    engine_install.add_argument("--confirmed", action="store_true")
    engine_install.add_argument("--execute", action="store_true")
    engine_update = sub.add_parser("engine-update-request")
    engine_update.add_argument("target_version")
    engine_update.add_argument("--hook-manifest", required=True)
    engine_update.add_argument("--manifest-root", default=None)
    engine_update.add_argument("--confirmed", action="store_true")
    engine_update.add_argument("--execute", action="store_true")
    engine_download = sub.add_parser("engine-download-request")
    engine_download.add_argument("target_version")
    engine_download.add_argument("--hook-manifest", required=True)
    engine_download.add_argument("--install-root", default=None)
    engine_download.add_argument("--allowed-root", default=None)
    engine_download.add_argument("--manifest-root", default=None)
    engine_download.add_argument("--confirmed", action="store_true")
    engine_download.add_argument("--execute", action="store_true")
    engine_verify_request = sub.add_parser("engine-verify-request")
    engine_verify_request.add_argument("--hook-manifest", required=True)
    engine_verify_request.add_argument("--manifest-root", default=None)
    engine_verify_request.add_argument("--confirmed", action="store_true")
    engine_verify_request.add_argument("--execute", action="store_true")
    engine_launch_request = sub.add_parser("engine-launch-request")
    engine_launch_request.add_argument("target_version")
    engine_launch_request.add_argument("project_path")
    engine_launch_request.add_argument("--allowed-root", required=True)
    engine_launch_request.add_argument("--hook-manifest", required=True)
    engine_launch_request.add_argument("--manifest-root", default=None)
    engine_launch_request.add_argument("--confirmed", action="store_true")
    engine_launch_request.add_argument("--execute", action="store_true")
    fab = sub.add_parser("fab-download-plan")
    fab.add_argument("asset_id")
    fab.add_argument("project_path")
    fab.add_argument("--allowed-root", required=True)
    fab.add_argument("--expected-price", type=float, default=0)
    fab.add_argument("--owned", action="store_true")
    fab_request = sub.add_parser("fab-download-request")
    fab_request.add_argument("asset_id")
    fab_request.add_argument("project_path")
    fab_request.add_argument("--allowed-root", required=True)
    fab_request.add_argument("--hook-manifest", required=True)
    fab_request.add_argument("--expected-price", type=float, default=0)
    fab_request.add_argument("--owned", action="store_true")
    fab_request.add_argument("--format", default="unreal-engine")
    fab_request.add_argument("--quality", default="")
    fab_request.add_argument("--confirmed", action="store_true")
    fab_request.add_argument("--execute", action="store_true")
    fab_download_batch = sub.add_parser("fab-download-batch-request")
    fab_download_batch.add_argument("project_path")
    fab_download_batch.add_argument("asset_ids", nargs="+", help="One or more Fab asset ids")
    fab_download_batch.add_argument("--allowed-root", required=True)
    fab_download_batch.add_argument("--hook-manifest", required=True)
    fab_download_batch.add_argument("--expected-price", type=float, default=0)
    fab_download_batch.add_argument("--owned", action="store_true")
    fab_download_batch.add_argument("--format", default="unreal-engine")
    fab_download_batch.add_argument("--quality", default="")
    fab_download_batch.add_argument("--confirmed", action="store_true")
    fab_download_batch.add_argument("--execute", action="store_true")
    fab_add_to_project = sub.add_parser("fab-add-to-project-request")
    fab_add_to_project.add_argument("asset_id")
    fab_add_to_project.add_argument("project_path")
    fab_add_to_project.add_argument("--allowed-root", required=True)
    fab_add_to_project.add_argument("--hook-manifest", required=True)
    fab_add_to_project.add_argument("--expected-price", type=float, default=0)
    fab_add_to_project.add_argument("--owned", action="store_true")
    fab_add_to_project.add_argument("--confirmed", action="store_true")
    fab_add_to_project.add_argument("--execute", action="store_true")
    fab_add_to_project_batch = sub.add_parser("fab-add-to-project-batch-request")
    fab_add_to_project_batch.add_argument("project_path")
    fab_add_to_project_batch.add_argument(
        "asset_ids", nargs="+", help="One or more Fab asset ids (max 100)"
    )
    fab_add_to_project_batch.add_argument("--allowed-root", required=True)
    fab_add_to_project_batch.add_argument("--hook-manifest", required=True)
    fab_add_to_project_batch.add_argument("--expected-price", type=float, default=0)
    fab_add_to_project_batch.add_argument("--owned", action="store_true")
    fab_add_to_project_batch.add_argument("--confirmed", action="store_true")
    fab_add_to_project_batch.add_argument("--execute", action="store_true")
    fab_export = sub.add_parser("fab-export-request")
    fab_export.add_argument("asset_id")
    fab_export.add_argument("destination")
    fab_export.add_argument("--allowed-root", required=True)
    fab_export.add_argument("--hook-manifest", required=True)
    fab_export.add_argument("--expected-price", type=float, default=0)
    fab_export.add_argument("--owned", action="store_true")
    fab_export.add_argument("--format", default="unreal-engine")
    fab_export.add_argument("--database", default=None)
    fab_export.add_argument("--confirmed", action="store_true")
    fab_export.add_argument("--execute", action="store_true")
    fab_import_request = sub.add_parser("fab-import-cached-request")
    fab_import_request.add_argument("asset_id")
    fab_import_request.add_argument("project_path")
    fab_import_request.add_argument("--allowed-root", required=True)
    fab_import_request.add_argument("--hook-manifest", required=True)
    fab_import_request.add_argument("--database", default=None)
    fab_import_request.add_argument(
        "--cache-root", dest="cache_roots", action="append", default=None
    )
    fab_import_request.add_argument("--destination-subdir", default="Fab")
    fab_import_request.add_argument("--confirmed", action="store_true")
    fab_import_request.add_argument("--execute", action="store_true")
    fab_import_all_request = sub.add_parser("fab-import-all-cached-request")
    fab_import_all_request.add_argument("project_path")
    fab_import_all_request.add_argument("--allowed-root", required=True)
    fab_import_all_request.add_argument("--hook-manifest", required=True)
    fab_import_all_request.add_argument(
        "--database", dest="databases", action="append", default=None
    )
    fab_import_all_request.add_argument(
        "--cache-root", dest="cache_roots", action="append", default=None
    )
    fab_import_all_request.add_argument("--destination-subdir", default="Fab")
    fab_import_all_request.add_argument("--confirmed", action="store_true")
    fab_import_all_request.add_argument("--execute", action="store_true")
    fab_asset = sub.add_parser("fab-asset-inspect")
    fab_asset.add_argument("asset_id")
    fab_asset.add_argument("--database", default=None)
    fab_search = sub.add_parser("fab-search")
    fab_search.add_argument("query", nargs="?", default="")
    fab_search.add_argument(
        "--database", dest="databases", action="append", default=None,
        help="Explicit listings_v1.db path; repeat for multiple indexes",
    )
    fab_search.add_argument(
        "--search-root", dest="search_roots", action="append", default=None,
        help="Root to scan read-only for listings_v1.db; repeat as needed",
    )
    fab_search.add_argument("--category", default="")
    fab_search.add_argument("--format", dest="formats", action="append", default=None)
    fab_search.add_argument("--owned-only", action="store_true")
    fab_search.add_argument("--downloaded-only", action="store_true")
    fab_search.add_argument("--max-depth", type=int, default=6)
    fab_download_status = sub.add_parser("fab-download-status")
    fab_download_status.add_argument("asset_id")
    fab_download_status.add_argument("--database", default=None)
    fab_download_status.add_argument(
        "--cache-root", dest="cache_roots", action="append", default=None,
        help="Approved VaultCache root; repeat for multiple Epic cache locations",
    )
    fab_import = sub.add_parser("fab-import-cached")
    fab_import.add_argument("asset_id")
    fab_import.add_argument("project_path")
    fab_import.add_argument("--allowed-root", required=True)
    fab_import.add_argument("--database", default=None)
    fab_import.add_argument(
        "--cache-root", dest="cache_roots", action="append", default=None,
        help="Approved VaultCache root; repeat to allow multiple Epic cache locations",
    )
    fab_import.add_argument("--destination-subdir", default="Fab")
    fab_import.add_argument("--confirmed", action="store_true")
    fab_import.add_argument("--execute", action="store_true")
    fab_import_all = sub.add_parser("fab-import-all-cached")
    fab_import_all.add_argument("project_path")
    fab_import_all.add_argument("--allowed-root", required=True)
    fab_import_all.add_argument(
        "--database", dest="databases", action="append", default=None,
        help="Explicit listings_v1.db path; repeat for multiple Epic cache indexes",
    )
    fab_import_all.add_argument(
        "--cache-root", dest="cache_roots", action="append", default=None,
        help="Approved VaultCache root; repeat to allow multiple Epic cache locations",
    )
    fab_import_all.add_argument("--confirmed", action="store_true")
    fab_import_all.add_argument("--execute", action="store_true")
    fab_inventory = sub.add_parser("fab-project-inventory")
    fab_inventory.add_argument("project_path")
    fab_inventory.add_argument("--allowed-root", required=True)
    fab_inventory.add_argument("--destination-subdir", default="Fab")
    fab_probe = sub.add_parser("fab-launcher-probe")
    fab_probe.add_argument("--editor-pid", type=int, required=True)
    fab_probe.add_argument("--port", type=int, default=DEFAULT_FAB_LAUNCHER_PORT)
    fab_status_probe = sub.add_parser("fab-launcher-status-probe")
    fab_status_probe.add_argument("--launcher-pid", type=int, required=True)
    fab_status_probe.add_argument("--port", type=int, default=DEFAULT_FAB_STATUS_PORT)
    fab_request = sub.add_parser("fab-launcher-import")
    fab_request.add_argument("payload", help="JSON file containing an assets list")
    fab_request.add_argument("--editor-pid", type=int, required=True)
    fab_request.add_argument("--editor-hwnd", type=int, required=True)
    fab_request.add_argument("--editor-executable", type=Path, required=True)
    fab_request.add_argument("--project-path", required=True)
    fab_request.add_argument("--allowed-root", required=True)
    fab_request.add_argument("--port", type=int, default=DEFAULT_FAB_LAUNCHER_PORT)
    fab_request.add_argument("--confirmed", action="store_true")
    fab_request.add_argument("--execute", action="store_true")
    hook_probe = sub.add_parser("hook-probe")
    hook_probe.add_argument("manifest_path")
    hook_invoke = sub.add_parser("hook-invoke")
    hook_invoke.add_argument("manifest_path")
    hook_invoke.add_argument("operation")
    hook_invoke.add_argument("--payload", default="{}")
    hook_invoke.add_argument("--confirmed", action="store_true")
    hook_invoke.add_argument("--execute", action="store_true")
    status = sub.add_parser("launcher-status")
    status.add_argument("--pid", type=int, required=True)
    status.add_argument("--hwnd", type=int, required=True)
    status.add_argument("--executable", type=Path, required=True)
    status.add_argument("--version", required=True)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    service = EpicService()
    if args.command == "capabilities":
        _dump(service.capabilities())
    elif args.command == "runtime-doctor":
        _dump(runtime_doctor())
    elif args.command == "hook-contract":
        from .hooks import hook_contract

        _dump(hook_contract())
    elif args.command == "engines":
        result = (
            service.list_engines(args.manifest_root)
            if args.manifest_root
            else service.list_engines()
        )
        _dump(result)
    elif args.command == "project-verify":
        _dump(service.verify_project(args.project_path, args.engine))
    elif args.command == "engine-verify":
        root = args.manifest_root or str(DEFAULT_MANIFEST_ROOT)
        _dump(service.verify_engines(root))
    elif args.command == "fab-library":
        database = args.database or str(DEFAULT_FAB_LIBRARY_DB)
        _dump(service.fab.list_local_library(database))
    elif args.command == "fab-library-sources":
        _dump(
            service.fab.list_local_libraries(
                args.databases,
                search_roots=args.search_roots,
                max_depth=args.max_depth,
            )
        )
    elif args.command == "engine-update-plan":
        root = args.manifest_root or str(DEFAULT_MANIFEST_ROOT)
        _dump(service.engine_update_plan(args.target_version, root).as_dict())
    elif args.command == "engine-download-plan":
        root = args.manifest_root or str(DEFAULT_MANIFEST_ROOT)
        _dump(service.engine_download_plan(args.target_version, root).as_dict())
    elif args.command == "engine-launch-plan":
        root = args.manifest_root or str(DEFAULT_MANIFEST_ROOT)
        _dump(service.engine_launch_plan(args.target_version, args.project_path, root).as_dict())
    elif args.command == "engine-install-request":
        _dump(
            service.engine_install_request(
                args.target_version,
                args.hook_manifest,
                install_root=args.install_root,
                allowed_root=args.allowed_root,
                manifest_root=args.manifest_root or str(DEFAULT_MANIFEST_ROOT),
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
        )
    elif args.command == "engine-update-request":
        _dump(
            service.engine_update_request(
                args.target_version,
                args.hook_manifest,
                manifest_root=args.manifest_root or str(DEFAULT_MANIFEST_ROOT),
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
        )
    elif args.command == "engine-download-request":
        _dump(
            service.engine_download_request(
                args.target_version,
                args.hook_manifest,
                install_root=args.install_root,
                allowed_root=args.allowed_root,
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
        )
    elif args.command == "engine-verify-request":
        _dump(
            service.engine_verify_request(
                args.hook_manifest,
                manifest_root=args.manifest_root or str(DEFAULT_MANIFEST_ROOT),
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
        )
    elif args.command == "engine-launch-request":
        _dump(
            service.engine_launch_request(
                args.target_version,
                args.project_path,
                args.allowed_root,
                args.hook_manifest,
                manifest_root=args.manifest_root or str(DEFAULT_MANIFEST_ROOT),
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
        )
    elif args.command == "fab-download-plan":
        _dump(
            service.fab.plan_download(
                args.asset_id,
                args.project_path,
                args.allowed_root,
                args.expected_price,
                args.owned,
            ).as_dict()
        )
    elif args.command == "fab-download-request":
        _dump(
            service.fab_download_request(
                args.asset_id,
                args.project_path,
                args.allowed_root,
                args.hook_manifest,
                expected_price=args.expected_price,
                owned=args.owned,
                format=args.format,
                quality=args.quality,
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
        )
    elif args.command == "fab-download-batch-request":
        _dump(
            service.fab_download_batch_request(
                args.asset_ids,
                args.project_path,
                args.allowed_root,
                args.hook_manifest,
                expected_price=args.expected_price,
                owned=args.owned,
                format=args.format,
                quality=args.quality,
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
        )
    elif args.command == "fab-add-to-project-request":
        _dump(
            service.fab_add_to_project_request(
                args.asset_id,
                args.project_path,
                args.allowed_root,
                args.hook_manifest,
                expected_price=args.expected_price,
                owned=args.owned,
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
        )
    elif args.command == "fab-add-to-project-batch-request":
        _dump(
            service.fab_add_to_project_batch_request(
                args.asset_ids,
                args.project_path,
                args.allowed_root,
                args.hook_manifest,
                expected_price=args.expected_price,
                owned=args.owned,
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
        )
    elif args.command == "fab-asset-inspect":
        database = args.database or str(DEFAULT_FAB_LIBRARY_DB)
        _dump(service.fab.inspect_local_asset(args.asset_id, database))
    elif args.command == "fab-search":
        _dump(
            service.fab.search_local_library(
                args.query,
                args.databases,
                search_roots=args.search_roots,
                category=args.category,
                formats=args.formats,
                owned_only=args.owned_only,
                downloaded_only=args.downloaded_only,
                max_depth=args.max_depth,
            )
        )
    elif args.command == "fab-download-status":
        database = args.database or str(DEFAULT_FAB_LIBRARY_DB)
        _dump(
            service.fab.inspect_download_state(
                args.asset_id,
                database,
                cache_roots=args.cache_roots,
            )
        )
    elif args.command == "fab-export-request":
        _dump(
            service.fab_export_request(
                args.asset_id,
                args.destination,
                args.allowed_root,
                args.hook_manifest,
                expected_price=args.expected_price,
                owned=args.owned,
                format=args.format,
                database_path=args.database,
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
        )
    elif args.command == "fab-import-cached-request":
        _dump(
            service.fab_import_cached_request(
                args.asset_id,
                args.project_path,
                args.allowed_root,
                args.hook_manifest,
                database_path=args.database,
                cache_roots=args.cache_roots,
                destination_subdir=args.destination_subdir,
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
        )
    elif args.command == "fab-import-all-cached-request":
        _dump(
            service.fab_import_all_cached_request(
                args.project_path,
                args.allowed_root,
                args.hook_manifest,
                database_paths=args.databases,
                cache_roots=args.cache_roots,
                destination_subdir=args.destination_subdir,
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
        )
    elif args.command == "fab-import-cached":
        database = args.database or str(DEFAULT_FAB_LIBRARY_DB)
        _dump(
            service.fab.plan_import_cached_asset(
                args.asset_id,
                args.project_path,
                args.allowed_root,
                database,
                cache_roots=args.cache_roots,
                destination_subdir=args.destination_subdir,
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
        )
    elif args.command == "fab-import-all-cached":
        _dump(
            service.fab.import_all_cached_assets(
                args.project_path,
                args.allowed_root,
                database_paths=args.databases,
                cache_roots=args.cache_roots,
                confirmed=args.confirmed,
                dry_run=not args.execute,
            )
        )
    elif args.command == "fab-project-inventory":
        _dump(
            service.fab.project_import_inventory(
                args.project_path,
                args.allowed_root,
                destination_subdir=args.destination_subdir,
            )
        )
    elif args.command == "project-import-request":
        _dump(
            service.project_import_request(
                args.project_path,
                args.source,
                args.allowed_root,
                args.hook_manifest,
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
        )
    elif args.command == "fab-launcher-probe":
        _dump(probe_fab_launcher(args.editor_pid, args.port))
    elif args.command == "fab-launcher-status-probe":
        _dump(probe_fab_status_listener(args.launcher_pid, args.port))
    elif args.command == "fab-launcher-import":
        try:
            payload = json.loads(Path(args.payload).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise SystemExit(f"payload must be a readable JSON file: {exc}") from exc
        if not isinstance(payload, dict):
            raise SystemExit("payload must be a JSON object containing an assets list")
        _dump(
            send_import_request(
                payload,
                editor_pid=args.editor_pid,
                editor_hwnd=args.editor_hwnd,
                editor_executable=args.editor_executable,
                project_path=args.project_path,
                allowed_root=args.allowed_root,
                port=args.port,
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
        )
    elif args.command == "hook-probe":
        _dump(service.hook_probe(args.manifest_path))
    elif args.command == "hook-invoke":
        try:
            payload = json.loads(args.payload)
        except ValueError as exc:
            raise SystemExit(f"--payload must be valid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise SystemExit("--payload must be a JSON object")
        _dump(
            service.hook_invoke(
                args.manifest_path,
                args.operation,
                payload,
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
        )
    elif args.command == "launcher-status":
        binding = LauncherBinding(args.pid, args.hwnd, args.executable, args.version)
        _dump(service.launcher_status(binding))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
