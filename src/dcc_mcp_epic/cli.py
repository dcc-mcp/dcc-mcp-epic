from __future__ import annotations

import argparse
import json
import sys
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
    worker_manifest = sub.add_parser(
        "fab-worker-manifest",
        help="Print or save a manifest for the built-in Fab provider worker",
    )
    worker_manifest.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write the manifest JSON to this path instead of stdout",
    )
    worker_manifest.add_argument("--timeout-seconds", type=int, default=120)
    engines = sub.add_parser("engines")
    engines.add_argument("--manifest-root", default=None)
    engine_verify = sub.add_parser("engine-verify")
    engine_verify.add_argument("--manifest-root", default=None)
    fab_library = sub.add_parser("fab-library")
    fab_library.add_argument("--database", default=None)
    fab_library_request = sub.add_parser("fab-library-request")
    fab_library_request.add_argument("--hook-manifest", required=True)
    fab_library_request.add_argument("--database", default=None)
    fab_library_request.add_argument("--confirmed", action="store_true")
    fab_library_request.add_argument("--execute", action="store_true")
    fab_add_library = sub.add_parser("fab-add-to-library-request")
    fab_add_library.add_argument("asset_id")
    fab_add_library.add_argument("--hook-manifest", required=True)
    fab_add_library.add_argument("--expected-price", type=float, default=0)
    fab_add_library.add_argument(
        "--free-listing",
        action="store_true",
        help="Explicitly assert that the current listing is free before account mutation",
    )
    fab_add_library.add_argument("--launcher-pid", type=int, default=None)
    fab_add_library.add_argument("--launcher-hwnd", type=int, default=None)
    fab_add_library.add_argument("--launcher-executable", type=Path, default=None)
    fab_add_library.add_argument("--confirmed", action="store_true")
    fab_add_library.add_argument("--execute", action="store_true")
    fab_add_library_batch = sub.add_parser("fab-add-to-library-batch-request")
    fab_add_library_batch.add_argument(
        "asset_ids", nargs="+", help="One or more Fab asset ids (max 100)"
    )
    fab_add_library_batch.add_argument("--hook-manifest", required=True)
    fab_add_library_batch.add_argument("--expected-price", type=float, default=0)
    fab_add_library_batch.add_argument(
        "--free-listing",
        action="store_true",
        help="Explicitly assert that the current listings are free before account mutation",
    )
    fab_add_library_batch.add_argument("--launcher-pid", type=int, default=None)
    fab_add_library_batch.add_argument("--launcher-hwnd", type=int, default=None)
    fab_add_library_batch.add_argument("--launcher-executable", type=Path, default=None)
    fab_add_library_batch.add_argument("--confirmed", action="store_true")
    fab_add_library_batch.add_argument("--execute", action="store_true")
    fab_library_sync = sub.add_parser("fab-library-sync-request")
    fab_library_sync.add_argument("--launcher-pid", type=int, required=True)
    fab_library_sync.add_argument("--allowed-root", required=True)
    fab_library_sync.add_argument("--hook-manifest", required=True)
    fab_library_sync.add_argument(
        "--database",
        dest="databases",
        action="append",
        default=None,
        help="Approved listings_v1.db path; repeat for multiple indexes",
    )
    fab_library_sync.add_argument(
        "--cache-root",
        dest="cache_roots",
        action="append",
        default=None,
        help="Approved VaultCache root; repeat for multiple locations",
    )
    fab_library_sync.add_argument("--confirmed", action="store_true")
    fab_library_sync.add_argument("--execute", action="store_true")
    fab_free_sync = sub.add_parser(
        "fab-free-assets-sync-request",
        help="Batch free Fab ownership, download, verification, and optional project import",
    )
    fab_free_sync.add_argument(
        "assets_json", type=Path, help="JSON file containing an assets array"
    )
    fab_free_sync.add_argument("--allowed-root", required=True)
    fab_free_sync.add_argument("--hook-manifest", required=True)
    fab_free_sync.add_argument(
        "--mode",
        choices=["library_only", "library_and_download", "library_download_and_project"],
        default="library_and_download",
    )
    fab_free_sync.add_argument("--project-path", default=None)
    fab_free_sync.add_argument("--launcher-pid", type=int, default=None)
    fab_free_sync.add_argument("--launcher-hwnd", type=int, default=None)
    fab_free_sync.add_argument("--launcher-executable", type=Path, default=None)
    fab_free_sync.add_argument("--launcher-version", default="")
    fab_free_sync.add_argument(
        "--database",
        dest="databases",
        action="append",
        default=None,
        help="Approved listings_v1.db path; repeat for multiple indexes",
    )
    fab_free_sync.add_argument(
        "--cache-root",
        dest="cache_roots",
        action="append",
        default=None,
        help="Approved VaultCache root; repeat for multiple locations",
    )
    fab_free_sync.add_argument("--confirmed", action="store_true")
    fab_free_sync.add_argument("--execute", action="store_true")
    fab_sources = sub.add_parser("fab-library-sources")
    fab_sources.add_argument(
        "--database",
        dest="databases",
        action="append",
        default=None,
        help="Explicit listings_v1.db path; repeat for multiple Epic cache indexes",
    )
    fab_sources.add_argument(
        "--search-root",
        dest="search_roots",
        action="append",
        default=None,
        help="Root to scan read-only for listings_v1.db; repeat as needed",
    )
    fab_sources.add_argument("--max-depth", type=int, default=6)
    fab_sources_request = sub.add_parser("fab-library-sources-request")
    fab_sources_request.add_argument("--hook-manifest", required=True)
    fab_sources_request.add_argument(
        "--database",
        dest="databases",
        action="append",
        default=None,
        help="Explicit listings_v1.db path; repeat for multiple Epic cache indexes",
    )
    fab_sources_request.add_argument(
        "--search-root",
        dest="search_roots",
        action="append",
        default=None,
        help="Root to scan read-only for listings_v1.db; repeat as needed",
    )
    fab_sources_request.add_argument("--max-depth", type=int, default=6)
    fab_sources_request.add_argument("--confirmed", action="store_true")
    fab_sources_request.add_argument("--execute", action="store_true")
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
    fab_asset_request = sub.add_parser("fab-asset-detail-request")
    fab_asset_request.add_argument("asset_id")
    fab_asset_request.add_argument("--hook-manifest", required=True)
    fab_asset_request.add_argument(
        "--database",
        dest="databases",
        action="append",
        default=None,
        help="Explicit listings_v1.db path; repeat for multiple indexes",
    )
    fab_asset_request.add_argument(
        "--search-root",
        dest="search_roots",
        action="append",
        default=None,
        help="Root to scan read-only for listings_v1.db; repeat as needed",
    )
    fab_asset_request.add_argument(
        "--cache-root",
        dest="cache_roots",
        action="append",
        default=None,
        help="Approved VaultCache root; repeat for multiple locations",
    )
    fab_asset_request.add_argument("--max-depth", type=int, default=6)
    fab_asset_request.add_argument("--confirmed", action="store_true")
    fab_asset_request.add_argument("--execute", action="store_true")
    fab_search = sub.add_parser("fab-search")
    fab_search.add_argument("query", nargs="?", default="")
    fab_search.add_argument(
        "--database",
        dest="databases",
        action="append",
        default=None,
        help="Explicit listings_v1.db path; repeat for multiple indexes",
    )
    fab_search.add_argument(
        "--search-root",
        dest="search_roots",
        action="append",
        default=None,
        help="Root to scan read-only for listings_v1.db; repeat as needed",
    )
    fab_search.add_argument("--category", default="")
    fab_search.add_argument("--format", dest="formats", action="append", default=None)
    fab_search.add_argument("--owned-only", action="store_true")
    fab_search.add_argument("--downloaded-only", action="store_true")
    fab_search.add_argument("--max-depth", type=int, default=6)
    fab_search_request = sub.add_parser("fab-search-request")
    fab_search_request.add_argument("query", nargs="?", default="")
    fab_search_request.add_argument("--hook-manifest", required=True)
    fab_search_request.add_argument(
        "--database",
        dest="databases",
        action="append",
        default=None,
        help="Explicit listings_v1.db path; repeat for multiple indexes",
    )
    fab_search_request.add_argument(
        "--search-root",
        dest="search_roots",
        action="append",
        default=None,
        help="Root to scan read-only for listings_v1.db; repeat as needed",
    )
    fab_search_request.add_argument("--category", default="")
    fab_search_request.add_argument("--format", dest="formats", action="append", default=None)
    fab_search_request.add_argument("--owned-only", action="store_true")
    fab_search_request.add_argument("--downloaded-only", action="store_true")
    fab_search_request.add_argument("--max-depth", type=int, default=6)
    fab_search_request.add_argument("--confirmed", action="store_true")
    fab_search_request.add_argument("--execute", action="store_true")
    fab_catalog_free = sub.add_parser(
        "fab-catalog-free-request",
        help="Read the current free Fab catalog through an official/native hook",
    )
    fab_catalog_free.add_argument("query", nargs="?", default="")
    fab_catalog_free.add_argument("--hook-manifest", required=True)
    fab_catalog_free.add_argument("--category", dest="categories", action="append", default=None)
    fab_catalog_free.add_argument("--format", dest="formats", action="append", default=None)
    fab_catalog_free.add_argument("--limit", type=int, default=100)
    fab_catalog_free.add_argument("--cursor", default="")
    fab_catalog_free.add_argument("--confirmed", action="store_true")
    fab_catalog_free.add_argument("--execute", action="store_true")
    fab_download_status = sub.add_parser("fab-download-status")
    fab_download_status.add_argument("asset_id")
    fab_download_status.add_argument("--database", default=None)
    fab_download_status.add_argument(
        "--cache-root",
        dest="cache_roots",
        action="append",
        default=None,
        help="Approved VaultCache root; repeat for multiple Epic cache locations",
    )
    fab_download_status_request = sub.add_parser("fab-download-status-request")
    fab_download_status_request.add_argument("asset_id")
    fab_download_status_request.add_argument("--hook-manifest", required=True)
    fab_download_status_request.add_argument("--database", default=None)
    fab_download_status_request.add_argument(
        "--cache-root",
        dest="cache_roots",
        action="append",
        default=None,
        help="Approved VaultCache root; repeat for multiple Epic cache locations",
    )
    fab_download_status_request.add_argument("--confirmed", action="store_true")
    fab_download_status_request.add_argument("--execute", action="store_true")
    fab_download_status_batch_request = sub.add_parser("fab-download-status-batch-request")
    fab_download_status_batch_request.add_argument(
        "asset_ids", nargs="+", help="One or more Fab asset ids (max 100)"
    )
    fab_download_status_batch_request.add_argument("--hook-manifest", required=True)
    fab_download_status_batch_request.add_argument(
        "--database",
        dest="databases",
        action="append",
        default=None,
        help="Explicit listings_v1.db path; repeat for multiple indexes",
    )
    fab_download_status_batch_request.add_argument(
        "--search-root",
        dest="search_roots",
        action="append",
        default=None,
        help="Root to scan read-only for listings_v1.db; repeat as needed",
    )
    fab_download_status_batch_request.add_argument(
        "--cache-root",
        dest="cache_roots",
        action="append",
        default=None,
        help="Approved VaultCache root; repeat for multiple locations",
    )
    fab_download_status_batch_request.add_argument("--max-depth", type=int, default=6)
    fab_download_status_batch_request.add_argument("--confirmed", action="store_true")
    fab_download_status_batch_request.add_argument("--execute", action="store_true")
    fab_import = sub.add_parser("fab-import-cached")
    fab_import.add_argument("asset_id")
    fab_import.add_argument("project_path")
    fab_import.add_argument("--allowed-root", required=True)
    fab_import.add_argument("--database", default=None)
    fab_import.add_argument(
        "--cache-root",
        dest="cache_roots",
        action="append",
        default=None,
        help="Approved VaultCache root; repeat to allow multiple Epic cache locations",
    )
    fab_import.add_argument("--destination-subdir", default="Fab")
    fab_import.add_argument("--confirmed", action="store_true")
    fab_import.add_argument("--execute", action="store_true")
    fab_import_all = sub.add_parser("fab-import-all-cached")
    fab_import_all.add_argument("project_path")
    fab_import_all.add_argument("--allowed-root", required=True)
    fab_import_all.add_argument(
        "--database",
        dest="databases",
        action="append",
        default=None,
        help="Explicit listings_v1.db path; repeat for multiple Epic cache indexes",
    )
    fab_import_all.add_argument(
        "--cache-root",
        dest="cache_roots",
        action="append",
        default=None,
        help="Approved VaultCache root; repeat to allow multiple Epic cache locations",
    )
    fab_import_all.add_argument("--confirmed", action="store_true")
    fab_import_all.add_argument("--execute", action="store_true")
    fab_inventory = sub.add_parser("fab-project-inventory")
    fab_inventory.add_argument("project_path")
    fab_inventory.add_argument("--allowed-root", required=True)
    fab_inventory.add_argument("--destination-subdir", default="Fab")
    fab_inventory_request = sub.add_parser("fab-import-inventory-request")
    fab_inventory_request.add_argument("project_path")
    fab_inventory_request.add_argument("--allowed-root", required=True)
    fab_inventory_request.add_argument("--hook-manifest", required=True)
    fab_inventory_request.add_argument("--destination-subdir", default="Fab")
    fab_inventory_request.add_argument("--confirmed", action="store_true")
    fab_inventory_request.add_argument("--execute", action="store_true")
    fab_probe = sub.add_parser("fab-launcher-probe")
    fab_probe.add_argument("--editor-pid", type=int, required=True)
    fab_probe.add_argument("--port", type=int, default=DEFAULT_FAB_LAUNCHER_PORT)
    fab_status_probe = sub.add_parser("fab-launcher-status-probe")
    fab_status_probe.add_argument("--launcher-pid", type=int, required=True)
    fab_status_probe.add_argument("--port", type=int, default=DEFAULT_FAB_STATUS_PORT)
    fab_status_request = sub.add_parser("fab-launcher-status-request")
    fab_status_request.add_argument("--launcher-pid", type=int, required=True)
    fab_status_request.add_argument("--hook-manifest", required=True)
    fab_status_request.add_argument("--port", type=int, default=DEFAULT_FAB_STATUS_PORT)
    fab_status_request.add_argument("--confirmed", action="store_true")
    fab_status_request.add_argument("--execute", action="store_true")
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
    status_request = sub.add_parser("launcher-status-request")
    status_request.add_argument("--pid", type=int, required=True)
    status_request.add_argument("--hwnd", type=int, required=True)
    status_request.add_argument("--executable", type=Path, required=True)
    status_request.add_argument("--version", required=True)
    status_request.add_argument("--hook-manifest", required=True)
    status_request.add_argument("--confirmed", action="store_true")
    status_request.add_argument("--execute", action="store_true")
    launcher_action = sub.add_parser("launcher-action-request")
    launcher_action.add_argument("--pid", type=int, required=True)
    launcher_action.add_argument("--hwnd", type=int, required=True)
    launcher_action.add_argument("--executable", type=Path, required=True)
    launcher_action.add_argument("--version", required=True)
    launcher_action.add_argument("--action-json", required=True)
    launcher_action.add_argument("--hook-manifest", required=True)
    launcher_action.add_argument("--confirmed", action="store_true")
    launcher_action.add_argument("--execute", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "fab-worker-manifest":
        from .providers.fab.worker import manifest

        value = manifest(python_executable=sys.executable, timeout_seconds=args.timeout_seconds)
        encoded = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        if args.output is None:
            print(encoded, end="")
        else:
            output = args.output.expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(encoded, encoding="utf-8")
            print(str(output))
        return 0
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
    elif args.command == "fab-library-request":
        _dump(
            service.fab_library_request(
                args.hook_manifest,
                database_path=args.database,
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
        )
    elif args.command == "fab-add-to-library-request":
        _dump(
            service.fab_add_to_library_request(
                args.asset_id,
                args.hook_manifest,
                expected_price=args.expected_price,
                free_listing=args.free_listing,
                launcher_pid=args.launcher_pid,
                launcher_hwnd=args.launcher_hwnd,
                launcher_executable=args.launcher_executable,
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
        )
    elif args.command == "fab-add-to-library-batch-request":
        _dump(
            service.fab_add_to_library_batch_request(
                args.asset_ids,
                args.hook_manifest,
                expected_price=args.expected_price,
                free_listing=args.free_listing,
                launcher_pid=args.launcher_pid,
                launcher_hwnd=args.launcher_hwnd,
                launcher_executable=args.launcher_executable,
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
        )
    elif args.command == "fab-library-sync-request":
        _dump(
            service.fab_library_sync_request(
                args.launcher_pid,
                args.allowed_root,
                args.hook_manifest,
                database_paths=args.databases,
                cache_roots=args.cache_roots,
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
        )
    elif args.command == "fab-free-assets-sync-request":
        try:
            assets_data = json.loads(args.assets_json.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise SystemExit(f"assets_json must be a readable JSON file: {exc}") from exc
        if isinstance(assets_data, dict):
            assets_data = assets_data.get("assets")
        if not isinstance(assets_data, list):
            raise SystemExit(
                "assets_json must contain a JSON array or an object with an assets array"
            )
        _dump(
            service.fab_free_assets_sync_request(
                assets_data,
                args.allowed_root,
                args.hook_manifest,
                mode=args.mode,
                project_path=args.project_path,
                launcher_pid=args.launcher_pid,
                launcher_hwnd=args.launcher_hwnd,
                launcher_executable=args.launcher_executable,
                launcher_version=args.launcher_version,
                database_paths=args.databases,
                cache_roots=args.cache_roots,
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
        )
    elif args.command == "fab-library-sources":
        _dump(
            service.fab.list_local_libraries(
                args.databases,
                search_roots=args.search_roots,
                max_depth=args.max_depth,
            )
        )
    elif args.command == "fab-library-sources-request":
        _dump(
            service.fab_library_sources_request(
                args.hook_manifest,
                database_paths=args.databases,
                search_roots=args.search_roots,
                max_depth=args.max_depth,
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
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
    elif args.command == "fab-asset-detail-request":
        _dump(
            service.fab_asset_detail_request(
                args.asset_id,
                args.hook_manifest,
                database_paths=args.databases,
                search_roots=args.search_roots,
                cache_roots=args.cache_roots,
                max_depth=args.max_depth,
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
        )
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
    elif args.command == "fab-search-request":
        _dump(
            service.fab_search_request(
                args.query,
                args.hook_manifest,
                database_paths=args.databases,
                search_roots=args.search_roots,
                category=args.category,
                formats=args.formats,
                owned_only=args.owned_only,
                downloaded_only=args.downloaded_only,
                max_depth=args.max_depth,
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
        )
    elif args.command == "fab-catalog-free-request":
        _dump(
            service.fab_catalog_free_request(
                args.hook_manifest,
                query=args.query,
                categories=args.categories,
                formats=args.formats,
                limit=args.limit,
                cursor=args.cursor,
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
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
    elif args.command == "fab-download-status-request":
        _dump(
            service.fab_download_status_request(
                args.asset_id,
                args.hook_manifest,
                database_path=args.database,
                cache_roots=args.cache_roots,
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
        )
    elif args.command == "fab-download-status-batch-request":
        _dump(
            service.fab_download_status_batch_request(
                args.asset_ids,
                args.hook_manifest,
                database_paths=args.databases,
                search_roots=args.search_roots,
                cache_roots=args.cache_roots,
                max_depth=args.max_depth,
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
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
    elif args.command == "fab-import-inventory-request":
        _dump(
            service.fab_import_inventory_request(
                args.project_path,
                args.allowed_root,
                args.hook_manifest,
                destination_subdir=args.destination_subdir,
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
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
    elif args.command == "fab-launcher-status-request":
        _dump(
            service.fab_launcher_status_request(
                args.launcher_pid,
                args.hook_manifest,
                port=args.port,
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
        )
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
    elif args.command == "launcher-status-request":
        binding = LauncherBinding(args.pid, args.hwnd, args.executable, args.version)
        _dump(
            service.launcher_status_request(
                binding,
                args.hook_manifest,
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
        )
    elif args.command == "launcher-action-request":
        try:
            action = json.loads(args.action_json)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"--action-json must be valid JSON: {exc}") from exc
        _dump(
            service.launcher_action_request(
                LauncherBinding(args.pid, args.hwnd, args.executable, args.version),
                action,
                args.hook_manifest,
                confirmed=args.confirmed,
                dry_run=not args.execute,
            ).as_dict()
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
