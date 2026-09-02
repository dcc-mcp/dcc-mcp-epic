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
