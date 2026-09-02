import hashlib
import json
import sys

from dcc_mcp_epic.models import CapabilityState
from dcc_mcp_epic.services import EpicService


def _hook_manifest(tmp_path, operations):
    hook = tmp_path / "hook.py"
    hook.write_text(
        "import json,sys; print(json.dumps({'received': json.load(sys.stdin)['payload']}))",
        encoding="utf-8",
    )
    manifest = tmp_path / "hook.json"
    manifest.write_text(
        json.dumps(
            {
                "protocol": "epic.hook.v1",
                "name": "typed-hook",
                "version": "1.0.0",
                "command": [sys.executable, str(hook)],
                "operations": operations,
                "requires_confirmation": [
                    item for item in operations if not item.endswith(".status")
                ],
                "sha256": hashlib.sha256(
                    (__import__("pathlib").Path(sys.executable)).read_bytes()
                ).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    return manifest


def _fab_db(path, rows):
    import sqlite3

    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE local_listing (uid TEXT, title TEXT, category_name TEXT, category_path TEXT)"
    )
    connection.execute(
        "CREATE TABLE download_meta (listing_uid TEXT, format TEXT, quality TEXT, "
        "path TEXT, cache_size INTEGER)"
    )
    connection.execute("CREATE TABLE listing_acquisition (listing_uid TEXT, user_uid TEXT)")
    for uid, title, category, fmt, cache_path, owned in rows:
        connection.execute(
            "INSERT INTO local_listing VALUES (?, ?, ?, '')", (uid, title, category)
        )
        connection.execute(
            "INSERT INTO download_meta VALUES (?, ?, '', ?, 1)",
            (uid, fmt, str(cache_path) if cache_path else ""),
        )
        if owned:
            connection.execute(
                "INSERT INTO listing_acquisition VALUES (?, 'user-1')", (uid,)
            )
    connection.commit()
    connection.close()


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


def test_fab_plan_rejects_project_traversal(tmp_path):
    result = EpicService().fab.plan_download(
        "asset-1", tmp_path.parent / "project", tmp_path, owned=True
    )
    assert result.state is CapabilityState.UNAVAILABLE
    assert "outside allowed root" in result.message


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


def test_local_fab_library_sources_merges_indexes_and_prefers_downloaded(tmp_path):
    import sqlite3

    def create_db(path, rows):
        connection = sqlite3.connect(path)
        connection.execute(
            "CREATE TABLE local_listing (uid TEXT, title TEXT, category_name TEXT, "
            "category_path TEXT)"
        )
        connection.execute(
            "CREATE TABLE download_meta (listing_uid TEXT, format TEXT, quality TEXT, "
            "path TEXT, cache_size INTEGER)"
        )
        connection.execute("CREATE TABLE listing_acquisition (listing_uid TEXT, user_uid TEXT)")
        for uid, title, cache_path in rows:
            connection.execute("INSERT INTO local_listing VALUES (?, ?, '', '')", (uid, title))
            connection.execute(
                "INSERT INTO download_meta VALUES (?, 'unreal-engine', '', ?, 10)",
                (uid, str(cache_path) if cache_path else ""),
            )
            connection.execute("INSERT INTO listing_acquisition VALUES (?, 'user-1')", (uid,))
        connection.commit()
        connection.close()

    downloaded = tmp_path / "downloaded"
    downloaded.mkdir()
    first = tmp_path / "first.db"
    second = tmp_path / "second.db"
    create_db(first, [("asset-1", "Asset", None), ("asset-2", "Other", downloaded)])
    create_db(second, [("asset-1", "Asset", downloaded)])

    result = EpicService().fab.list_local_libraries([first, second])
    assert result["read_only"] is True
    assert result["database_count"] == 2
    assert result["unique_asset_count"] == 2
    merged = {item["uid"]: item for item in result["assets"]}
    assert merged["asset-1"]["downloaded"] is True
    assert merged["asset-1"]["database_path"] == str(second.resolve())


def test_fab_download_status_rechecks_cache_path(tmp_path):
    import sqlite3

    cache_root = tmp_path / "VaultCache"
    cache = cache_root / "Asset"
    cache.mkdir(parents=True)
    database = tmp_path / "listings_v1.db"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE local_listing (uid TEXT, title TEXT, category_name TEXT, "
        "category_path TEXT)"
    )
    connection.execute(
        "CREATE TABLE download_meta (listing_uid TEXT, format TEXT, quality TEXT, "
        "path TEXT, cache_size INTEGER)"
    )
    connection.execute("CREATE TABLE listing_acquisition (listing_uid TEXT, user_uid TEXT)")
    connection.execute("INSERT INTO local_listing VALUES ('asset-1', 'Asset', '', '')")
    connection.execute(
        "INSERT INTO download_meta VALUES ('asset-1', 'fbx', '', ?, 4)", (str(cache),)
    )
    connection.execute("INSERT INTO listing_acquisition VALUES ('asset-1', 'user-1')")
    connection.commit()
    connection.close()
    result = EpicService().fab.inspect_download_state(
        "asset-1", database, cache_roots=[cache_root]
    )
    assert result["read_only"] is True
    assert result["state"] == "downloaded"
    assert result["cache_path_verified"] is True


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


def test_import_accepts_explicit_second_cache_root(tmp_path):
    import sqlite3

    cache_root = tmp_path / "second-vault"
    cache = cache_root / "AssetCache"
    content = cache / "Content"
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
    connection.execute(
        "INSERT INTO download_meta VALUES ('asset-1', 'unreal-engine', '', ?, 1)",
        (str(cache),),
    )
    connection.execute("INSERT INTO listing_acquisition VALUES ('asset-1', 'user-1')")
    connection.commit()
    connection.close()
    project = tmp_path / "project"
    (project / "Content").mkdir(parents=True)
    result = EpicService().fab.plan_import_cached_asset(
        "asset-1",
        project,
        tmp_path,
        database,
        cache_roots=[cache_root],
    )
    assert result.state is CapabilityState.READ_ONLY


def test_import_supports_fab_source_files_and_textures(tmp_path):
    import sqlite3

    cache_root = tmp_path / "VaultCache"
    source = cache_root / "FabLibrary" / "Armor" / "extracted"
    (source / "textures").mkdir(parents=True)
    (source / "source").mkdir()
    (source / "source" / "FemaleArmor.fbx").write_bytes(b"fbx")
    (source / "textures" / "Base_color.png").write_bytes(b"png")
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
    connection.execute("INSERT INTO local_listing VALUES ('asset-1', 'Armor', '', '')")
    connection.execute(
        "INSERT INTO download_meta VALUES ('asset-1', 'fbx', '', ?, 1)", (str(source),)
    )
    connection.execute("INSERT INTO listing_acquisition VALUES ('asset-1', 'user-1')")
    connection.commit()
    connection.close()
    project = tmp_path / "project"
    (project / "Content").mkdir(parents=True)
    service = EpicService()
    result = service.fab.plan_import_cached_asset(
        "asset-1", project, tmp_path, database, cache_roots=[cache_root]
    )
    assert result.state is CapabilityState.READ_ONLY
    assert result.details["import_mode"] == "source-files"
    assert result.details["file_count"] == 2


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


def test_fab_download_request_dispatches_only_after_free_owned_policy(tmp_path):
    import hashlib
    import sys

    hook = tmp_path / "hook.py"
    hook.write_text(
        "import json,sys; print(json.dumps({'received': json.load(sys.stdin)['payload']}))",
        encoding="utf-8",
    )
    manifest = tmp_path / "hook.json"
    digest = hashlib.sha256((__import__("pathlib").Path(sys.executable)).read_bytes()).hexdigest()
    manifest.write_text(
        json.dumps(
            {
                "protocol": "epic.hook.v1",
                "name": "download-hook",
                "version": "1.0.0",
                "command": [sys.executable, str(hook)],
                "operations": ["fab.download.request"],
                "requires_confirmation": ["fab.download.request"],
                "sha256": digest,
            }
        ),
        encoding="utf-8",
    )
    project = tmp_path / "project"
    (project / "Content").mkdir(parents=True)
    service = EpicService()
    blocked = service.fab_download_request(
        "asset-1", project, tmp_path, manifest, owned=False
    )
    assert blocked.state is CapabilityState.HUMAN_REQUIRED
    dry_run = service.fab_download_request(
        "asset-1", project, tmp_path, manifest, owned=True
    )
    assert dry_run.state is CapabilityState.HUMAN_REQUIRED
    dry_run = service.fab_download_request(
        "asset-1", project, tmp_path, manifest, owned=True, confirmed=True
    )
    assert dry_run.state is CapabilityState.READ_ONLY
    assert dry_run.details["hook"]["details"]["side_effects_performed"] is False
    executed = service.fab_download_request(
        "asset-1",
        project,
        tmp_path,
        manifest,
        owned=True,
        confirmed=True,
        dry_run=False,
    )
    assert executed.state is CapabilityState.AVAILABLE
    assert executed.details["side_effects_performed"] is True
    assert executed.details["hook"]["details"]["response"]["received"]["format"] == "unreal-engine"


def test_fab_search_filters_merged_local_indexes(tmp_path):
    first = tmp_path / "first.db"
    second = tmp_path / "second.db"
    cache = tmp_path / "cache"
    cache.mkdir()
    _fab_db(
        first,
        [
            ("asset-1", "Free Arrow Trail", "VFX", "unreal-engine", cache, True),
            ("asset-2", "Medieval House", "Environment", "fbx", None, True),
        ],
    )
    _fab_db(
        second,
        [("asset-1", "Free Arrow Trail", "VFX", "unreal-engine", cache, True)],
    )
    result = EpicService().fab.search_local_library(
        "arrow", [first, second], formats=["unreal-engine"], downloaded_only=True
    )
    assert result["read_only"] is True
    assert result["result_count"] == 1
    assert result["assets"][0]["uid"] == "asset-1"


def test_hook_contract_describes_mutation_and_required_fields():
    from dcc_mcp_epic.hooks import hook_contract

    contract = hook_contract()
    operations = {item["name"]: item for item in contract["operations"]}
    assert contract["protocol"] == "epic.hook.v1"
    assert operations["fab.download.request"]["mutating"] is True
    assert operations["fab.download.request"]["required_fields"] == [
        "asset_id",
        "project_path",
        "format",
    ]
    assert operations["fab.download_batch.request"]["mutating"] is True
    assert operations["fab.add_to_project.request"]["mutating"] is True
    assert operations["fab.add_to_project.request"]["required_fields"] == [
        "asset_id",
        "project_path",
    ]
    assert operations["fab.add_to_project_batch.request"]["mutating"] is True
    assert operations["fab.add_to_project_batch.request"]["required_fields"] == [
        "assets",
        "project_path",
    ]
    assert operations["fab.library_sources.request"]["mutating"] is False


def test_typed_engine_download_request_is_dry_run_by_default(tmp_path):
    manifest = _hook_manifest(tmp_path, ["engine.download.request"])
    result = EpicService().engine_download_request(
        "5.5",
        manifest,
        allowed_root=tmp_path,
        install_root=tmp_path / "UE_5.5",
        confirmed=True,
    )
    assert result.state is CapabilityState.READ_ONLY
    assert result.operation == "engine.download.request"
    assert result.details["payload"]["target_version"] == "5.5"


def test_typed_fab_download_batch_is_bounded_and_dry_run(tmp_path):
    manifest = _hook_manifest(tmp_path, ["fab.download_batch.request"])
    project = tmp_path / "project"
    project.mkdir()
    result = EpicService().fab_download_batch_request(
        ["asset-1", "asset-2"],
        project,
        tmp_path,
        manifest,
        owned=True,
        format="fbx",
        confirmed=True,
    )
    assert result.state is CapabilityState.READ_ONLY
    assert result.operation == "fab.download_batch.request"
    assert [item["asset_id"] for item in result.details["payload"]["assets"]] == [
        "asset-1",
        "asset-2",
    ]


def test_typed_fab_download_batch_rejects_duplicates(tmp_path):
    manifest = tmp_path / "missing-hook.json"
    result = EpicService().fab_download_batch_request(
        ["asset-1", "asset-1"], tmp_path, tmp_path, manifest, owned=True
    )
    assert result.state is CapabilityState.UNAVAILABLE
    assert "duplicates" in result.message


def test_typed_fab_download_batch_rejects_unreal_native(tmp_path):
    manifest = tmp_path / "missing-hook.json"
    result = EpicService().fab_download_batch_request(
        ["asset-1"], tmp_path, tmp_path, manifest, owned=True
    )
    assert result.state is CapabilityState.UNAVAILABLE
    assert result.details["next_operation"] == "fab.add_to_project.request"


def test_typed_fab_add_to_project_request_is_dry_run(tmp_path):
    manifest = _hook_manifest(tmp_path, ["fab.add_to_project.request"])
    project = tmp_path / "project"
    project.mkdir()
    result = EpicService().fab_add_to_project_request(
        "asset-1", project, tmp_path, manifest, owned=True, confirmed=True
    )
    assert result.state is CapabilityState.READ_ONLY
    assert result.operation == "fab.add_to_project.request"
    assert result.details["payload"]["action"] == "add_to_project"
    assert result.details["payload"]["format"] == "unreal-engine"
    assert result.details["side_effects_performed"] is False


def test_typed_fab_add_to_project_batch_is_bounded_and_dry_run(tmp_path):
    manifest = _hook_manifest(tmp_path, ["fab.add_to_project_batch.request"])
    project = tmp_path / "project"
    project.mkdir()
    result = EpicService().fab_add_to_project_batch_request(
        ["asset-1", "asset-2"],
        project,
        tmp_path,
        manifest,
        owned=True,
        confirmed=True,
    )
    assert result.state is CapabilityState.READ_ONLY
    assert result.operation == "fab.add_to_project_batch.request"
    assert [item["asset_id"] for item in result.details["payload"]["assets"]] == [
        "asset-1",
        "asset-2",
    ]
    assert result.details["payload"]["execution_contract"] == (
        "one official Add to Project action per asset"
    )
    assert result.details["side_effects_performed"] is False


def test_typed_fab_add_to_project_batch_rejects_duplicates(tmp_path):
    result = EpicService().fab_add_to_project_batch_request(
        ["asset-1", "asset-1"], tmp_path, tmp_path, tmp_path / "missing-hook.json", owned=True
    )
    assert result.state is CapabilityState.UNAVAILABLE
    assert "duplicates" in result.message


def test_typed_engine_install_request_requires_scope_for_install_root(tmp_path):
    manifest = tmp_path / "missing-hook.json"
    result = EpicService().engine_install_request(
        "5.5", manifest, install_root=tmp_path / "UE"
    )
    assert result.state is CapabilityState.HUMAN_REQUIRED
    assert "allowed_root" in result.message


def test_typed_fab_export_request_enforces_free_owned_policy(tmp_path):
    manifest = tmp_path / "missing-hook.json"
    result = EpicService().fab_export_request(
        "asset-1", tmp_path / "out", tmp_path, manifest, owned=False
    )
    assert result.state is CapabilityState.HUMAN_REQUIRED
    assert "ownership" in result.message


def test_project_import_request_rejects_source_traversal(tmp_path):
    manifest = tmp_path / "missing-hook.json"
    result = EpicService().project_import_request(
        tmp_path / "project",
        tmp_path.parent / "outside.fbx",
        tmp_path,
        manifest,
    )
    assert result.state is CapabilityState.UNAVAILABLE
    assert "outside allowed root" in result.message
