from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Optional

from .models import LauncherBinding
from .providers.epic_launcher.manifest import DEFAULT_MANIFEST_ROOT
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
    fab = sub.add_parser("fab-download-plan")
    fab.add_argument("asset_id")
    fab.add_argument("project_path")
    fab.add_argument("--allowed-root", required=True)
    fab.add_argument("--expected-price", type=float, default=0)
    fab.add_argument("--owned", action="store_true")
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
    elif args.command == "launcher-status":
        binding = LauncherBinding(args.pid, args.hwnd, args.executable, args.version)
        _dump(service.launcher_status(binding))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
