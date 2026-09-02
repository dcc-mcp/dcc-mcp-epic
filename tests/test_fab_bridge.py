import os
import socket

from dcc_mcp_epic.providers.fab.bridge import (
    probe_fab_launcher,
    probe_fab_status_listener,
    validate_import_payload,
)


def test_validate_fab_launcher_payload_requires_existing_supported_files(tmp_path):
    source = tmp_path / "asset.fbx"
    source.write_bytes(b"fbx")
    asset = {
        "id": "asset-1",
        "path": str(source),
        "native_files": [str(source)],
        "additional_textures": [],
        "meshes": [],
        "materials": [],
        "metadata": {
            "fab": {"isQuixel": False, "listing": {}},
            "launcher": {"version": "0.5.0", "listening_port": 23429},
            "megascans": {},
        },
    }
    evidence = validate_import_payload(
        {"assets": [asset]},
        tmp_path,
    )
    assert evidence["asset_count"] == 1
    assert evidence["assets"][0]["path_count"] == 2


def test_validate_fab_launcher_payload_rejects_traversal_and_unknown_extension(tmp_path):
    import pytest

    with pytest.raises(ValueError, match="outside allowed root"):
        validate_import_payload(
            {
                "assets": [
                    {
                        "id": "asset-1",
                        "path": str(tmp_path.parent / "asset.fbx"),
                        "native_files": [],
                        "additional_textures": [],
                        "meshes": [],
                        "materials": [],
                        "metadata": {},
                    }
                ]
            },
            tmp_path,
        )
    unsupported = tmp_path / "asset.exe"
    unsupported.write_bytes(b"exe")
    with pytest.raises(ValueError, match="unsupported"):
        validate_import_payload(
            {
                "assets": [
                    {
                        "id": "asset-1",
                        "path": str(unsupported),
                        "native_files": [],
                        "additional_textures": [],
                        "meshes": [],
                        "materials": [],
                        "metadata": {
                            "fab": {"isQuixel": False, "listing": {}},
                            "launcher": {"version": "0.5.0", "listening_port": 23429},
                            "megascans": {},
                        },
                    }
                ]
            },
            tmp_path,
        )


def test_probe_fab_launcher_reports_listener_for_bound_pid():
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        evidence = probe_fab_launcher(os.getpid(), listener.getsockname()[1])
        assert evidence["listening"] is True
        assert "127.0.0.1" in evidence["addresses"]
    finally:
        listener.close()


def test_probe_fab_status_listener_reports_callback_listener_for_bound_pid():
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        evidence = probe_fab_status_listener(os.getpid(), listener.getsockname()[1])
        assert evidence["listening"] is True
        assert evidence["protocol"] == "fablauncher.status.v1"
        assert evidence["direction"].startswith("Launcher receives")
    finally:
        listener.close()
