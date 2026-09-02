import json

from dcc_mcp_epic.providers.epic_launcher.manifest import list_engine_installs


def test_list_engine_installs_is_read_only(tmp_path):
    manifest = tmp_path / "engine.item"
    manifest.write_text(
        json.dumps(
            {
                "AppName": "UE_5.5",
                "AppVersionString": "5.5.4-test",
                "InstallLocation": "F:/UE/UE_5.5",
                "bIsIncompleteInstall": False,
                "InstallSize": 123,
            }
        ),
        encoding="utf-8",
    )
    before = manifest.read_bytes()
    entries = list_engine_installs(tmp_path)
    assert len(entries) == 1
    assert entries[0].app_name == "UE_5.5"
    assert entries[0].install_size == 123
    assert manifest.read_bytes() == before


def test_non_engine_entries_are_ignored(tmp_path):
    (tmp_path / "other.item").write_text(json.dumps({"AppName": "Fortnite"}), encoding="utf-8")
    assert list_engine_installs(tmp_path) == []
