import json

from dcc_mcp_epic.models import CapabilityState
from dcc_mcp_epic.services import EpicService


def test_engine_update_plan_is_explicitly_no_side_effect(tmp_path):
    (tmp_path / "engine.item").write_text(
        json.dumps(
            {
                "AppName": "UE_5.5",
                "AppVersionString": "5.5.4-test",
                "InstallLocation": "F:/UE/UE_5.5",
                "bIsIncompleteInstall": False,
            }
        ),
        encoding="utf-8",
    )
    result = EpicService().engine_update_plan("5.5", tmp_path)
    assert result.state is CapabilityState.HUMAN_REQUIRED
    assert result.details["side_effects_performed"] is False
    assert result.details["already_installed"]


def test_fab_plan_requires_ownership_and_allowed_root(tmp_path):
    service = EpicService()
    result = service.fab.plan_download("asset-1", tmp_path / "project", tmp_path)
    assert result.state is CapabilityState.HUMAN_REQUIRED
    assert "ownership" in result.message


def test_project_verify_targets_ue_55(tmp_path):
    project = tmp_path / "RiftKidsARPG.uproject"
    project.write_text(json.dumps({"EngineAssociation": "5.5", "Plugins": []}), encoding="utf-8")
    assert EpicService().verify_project(project)["ok"] is True


def test_local_fab_library_is_read_only(tmp_path):
    import sqlite3

    database = tmp_path / "listings_v1.db"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE local_listing (uid TEXT, title TEXT, category_name TEXT, category_path TEXT)"
    )
    connection.execute(
        "CREATE TABLE download_meta (listing_uid TEXT, format TEXT, quality TEXT, "
        "path TEXT, cache_size INTEGER)"
    )
    connection.execute("INSERT INTO local_listing VALUES ('asset-1', 'Free Arrow Trail', '', '')")
    connection.execute(
        "INSERT INTO download_meta VALUES ('asset-1', 'unreal-engine', '', ?, 10)",
        (str(tmp_path),),
    )
    connection.commit()
    connection.close()
    before = database.read_bytes()
    result = EpicService().fab.list_local_library(database)
    assert result["assets"][0]["title"] == "Free Arrow Trail"
    assert result["read_only"] is True
    assert database.read_bytes() == before


def test_import_cached_asset_is_dry_run_then_idempotent(tmp_path, monkeypatch):
    import sqlite3

    cache_root = tmp_path / "VaultCache"
    cache = cache_root / "ArrowTrailCache"
    content = cache / "data" / "Content" / "ArrowTrail" / "FX"
    content.mkdir(parents=True)
    (content / "NS_ArrowTrail.uasset").write_bytes(b"uasset-data")
    database = tmp_path / "listings_v1.db"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE local_listing (uid TEXT, title TEXT, category_name TEXT, category_path TEXT)"
    )
    connection.execute(
        "CREATE TABLE download_meta (listing_uid TEXT, format TEXT, quality TEXT, "
        "path TEXT, cache_size INTEGER)"
    )
    connection.execute("CREATE TABLE listing_acquisition (listing_uid TEXT, user_uid TEXT)")
    connection.execute("INSERT INTO local_listing VALUES ('asset-1', 'Free Arrow Trail', '', '')")
    connection.execute(
        "INSERT INTO download_meta VALUES ('asset-1', 'unreal-engine', '', ?, 10)",
        (str(cache),),
    )
    connection.execute("INSERT INTO listing_acquisition VALUES ('asset-1', 'user-1')")
    connection.commit()
    connection.close()

    project = tmp_path / "project"
    (project / "Content").mkdir(parents=True)
    monkeypatch.setattr(
        "dcc_mcp_epic.providers.fab.service.DEFAULT_FAB_CACHE_ROOT", cache_root.resolve()
    )
    service = EpicService()
    planned = service.fab.plan_import_cached_asset("asset-1", project, tmp_path, database)
    assert planned.state is CapabilityState.READ_ONLY
    assert planned.details["file_count"] == 1
    assert not (project / "Content" / "Fab").exists()

    imported = service.fab.plan_import_cached_asset(
        "asset-1", project, tmp_path, database, confirmed=True, dry_run=False
    )
    assert imported.state is CapabilityState.AVAILABLE
    destination = project / "Content" / "Fab" / "Free_Arrow_Trail-asset-1"
    assert (destination / "ArrowTrail" / "FX" / "NS_ArrowTrail.uasset").is_file()
    assert (destination / ".dcc-mcp-fab.json").is_file()

    repeated = service.fab.plan_import_cached_asset("asset-1", project, tmp_path, database)
    assert repeated.state is CapabilityState.AVAILABLE
    assert repeated.details["already_imported"] is True


def test_import_rejects_cache_path_outside_vault(tmp_path):
    import sqlite3

    cache = tmp_path / "outside"
    content = cache / "data" / "Content"
    content.mkdir(parents=True)
    (content / "Asset.uasset").write_bytes(b"asset")
    database = tmp_path / "listings_v1.db"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE local_listing (uid TEXT, title TEXT, category_name TEXT, category_path TEXT)"
    )
    connection.execute(
        "CREATE TABLE download_meta (listing_uid TEXT, format TEXT, quality TEXT, "
        "path TEXT, cache_size INTEGER)"
    )
    connection.execute("CREATE TABLE listing_acquisition (listing_uid TEXT, user_uid TEXT)")
    connection.execute("INSERT INTO local_listing VALUES ('asset-1', 'Asset', '', '')")
    connection.execute("INSERT INTO download_meta VALUES ('asset-1', '', '', ?, 1)", (str(cache),))
    connection.execute("INSERT INTO listing_acquisition VALUES ('asset-1', 'user-1')")
    connection.commit()
    connection.close()
    (tmp_path / "project" / "Content").mkdir(parents=True)
    result = EpicService().fab.plan_import_cached_asset(
        "asset-1", tmp_path / "project", tmp_path, database
    )
    assert result.state is CapabilityState.UNAVAILABLE
    assert "outside" in result.message


def test_project_import_inventory_verifies_manifest_hashes(tmp_path):
    import hashlib
    import json

    project = tmp_path / "project"
    destination = project / "Content" / "Fab" / "Hero-asset-1"
    destination.mkdir(parents=True)
    target = destination / "Meshes" / "hero.uasset"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"hero")
    manifest = {
        "schema": "dcc-mcp-epic.fab-import.v1",
        "asset_id": "asset-1",
        "files": [
            {
                "path": "Meshes/hero.uasset",
                "size": 4,
                "sha256": hashlib.sha256(b"hero").hexdigest(),
            }
        ],
    }
    (destination / ".dcc-mcp-fab.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    service = EpicService()
    inventory = service.fab.project_import_inventory(project, tmp_path)
    assert inventory["all_valid"] is True
    assert inventory["asset_count"] == 1
    assert inventory["file_count"] == 1
    target.write_bytes(b"tampered")
    inventory = service.fab.project_import_inventory(project, tmp_path)
    assert inventory["all_valid"] is False
    assert inventory["assets"][0]["mismatched_files"] == ["Meshes/hero.uasset"]
