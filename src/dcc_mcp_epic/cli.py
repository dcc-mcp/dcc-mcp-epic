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
    engines = sub.add_parser("engines")
    engines.add_argument("--manifest-root", default=None)
    engine_verify = sub.add_parser("engine-verify")
    engine_verify.add_argument("--manifest-root", default=None)
    fab_library = sub.add_parser("fab-library")
    fab_library.add_argument("--database", default=None)
    project = sub.add_parser("project-verify")
    project.add_argument("project_path")
    project.add_argument("--engine", default="5.5")
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
    fab = sub.add_parser("fab-download-plan")
    fab.add_argument("asset_id")
    fab.add_argument("project_path")
    fab.add_argument("--allowed-root", required=True)
    fab.add_argument("--expected-price", type=float, default=0)
    fab.add_argument("--owned", action="store_true")
    fab_asset = sub.add_parser("fab-asset-inspect")
    fab_asset.add_argument("asset_id")
    fab_asset.add_argument("--database", default=None)
    fab_import = sub.add_parser("fab-import-cached")
    fab_import.add_argument("asset_id")
    fab_import.add_argument("project_path")
    fab_import.add_argument("--allowed-root", required=True)
    fab_import.add_argument("--database", default=None)
    fab_import.add_argument("--destination-subdir", default="Fab")
    fab_import.add_argument("--confirmed", action="store_true")
    fab_import.add_argument("--execute", action="store_true")
    fab_import_all = sub.add_parser("fab-import-all-cached")
    fab_import_all.add_argument("project_path")
    fab_import_all.add_argument("--allowed-root", required=True)
    fab_import_all.add_argument("--database", default=None)
    fab_import_all.add_argument("--confirmed", action="store_true")
    fab_import_all.add_argument("--execute", action="store_true")
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
    elif args.command == "engine-update-plan":
        root = args.manifest_root or str(DEFAULT_MANIFEST_ROOT)
        _dump(service.engine_update_plan(args.target_version, root).as_dict())
    elif args.command == "engine-download-plan":
        root = args.manifest_root or str(DEFAULT_MANIFEST_ROOT)
        _dump(service.engine_download_plan(args.target_version, root).as_dict())
    elif args.command == "engine-launch-plan":
        root = args.manifest_root or str(DEFAULT_MANIFEST_ROOT)
        _dump(service.engine_launch_plan(args.target_version, args.project_path, root).as_dict())
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
    elif args.command == "fab-asset-inspect":
        database = args.database or str(DEFAULT_FAB_LIBRARY_DB)
        _dump(service.fab.inspect_local_asset(args.asset_id, database))
    elif args.command == "fab-import-cached":
        database = args.database or str(DEFAULT_FAB_LIBRARY_DB)
        _dump(
            service.fab.plan_import_cached_asset(
                args.asset_id,
                args.project_path,
                args.allowed_root,
                database,
                destination_subdir=args.destination_subdir,
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
        )
    elif args.command == "fab-import-all-cached":
        database = args.database or str(DEFAULT_FAB_LIBRARY_DB)
        _dump(
            service.fab.import_all_cached_assets(
                args.project_path,
                args.allowed_root,
                database,
                confirmed=args.confirmed,
                dry_run=not args.execute,
            )
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
