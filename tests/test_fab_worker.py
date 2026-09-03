import json
import sys

from dcc_mcp_epic.hooks import HOOK_PROTOCOL, invoke_hook, load_hook_manifest
from dcc_mcp_epic.models import CapabilityState
from dcc_mcp_epic.providers.fab.worker import FabWorker, manifest


def test_worker_reads_local_library_without_provider(tmp_path):
    response = FabWorker().handle(
        {
            "protocol": HOOK_PROTOCOL,
            "operation": "fab.library.request",
            "payload": {"database_path": str(tmp_path / "missing.db")},
        }
    )

    assert response["state"] == CapabilityState.READ_ONLY.value
    assert response["details"]["assets"] == []
    assert response["details"]["side_effects_performed"] is False


def test_worker_filters_explicitly_free_catalog_snapshot(tmp_path, monkeypatch):
    snapshot = tmp_path / "catalog.json"
    snapshot.write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "asset_id": "free-vfx",
                        "title": "Free VFX",
                        "price": 0,
                        "free_listing": True,
                        "category": "VFX",
                        "formats": ["unreal-engine"],
                    },
                    {
                        "asset_id": "paid-vfx",
                        "title": "Paid VFX",
                        "price": 4.99,
                        "free_listing": False,
                        "category": "VFX",
                        "formats": ["unreal-engine"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DCC_MCP_EPIC_FAB_CATALOG_JSON", str(snapshot))
    response = FabWorker().handle(
        {
            "protocol": HOOK_PROTOCOL,
            "operation": "fab.catalog_free.request",
            "payload": {
                "free_only": True,
                "limit": 10,
                "categories": ["vfx"],
            },
        }
    )

    assert response["state"] == CapabilityState.READ_ONLY.value
    assert [item["asset_id"] for item in response["details"]["assets"]] == ["free-vfx"]
    assert response["details"]["total_count"] == 1


def test_worker_does_not_claim_account_mutation_without_provider(tmp_path):
    response = FabWorker().handle(
        {
            "protocol": HOOK_PROTOCOL,
            "operation": "fab.free_assets_sync.request",
            "payload": {
                "assets": [
                    {
                        "asset_id": "free-vfx",
                        "expected_price": 0,
                        "free_listing": True,
                        "format": "unreal-engine",
                    }
                ],
                "allowed_root": str(tmp_path),
                "mode": "library_and_download",
                "free_only": True,
            },
        }
    )

    assert response["state"] == CapabilityState.UNAVAILABLE.value
    assert response["details"]["code"] == "official_provider_not_configured"
    assert response["details"]["side_effects_performed"] is False


def test_invoke_hook_propagates_typed_worker_state(tmp_path):
    path = tmp_path / "fab-worker.json"
    path.write_text(json.dumps(manifest()), encoding="utf-8")
    spec = load_hook_manifest(path)
    result = invoke_hook(
        spec,
        "fab.free_assets_sync.request",
        {
            "assets": [
                {
                    "asset_id": "free-vfx",
                    "expected_price": 0,
                    "free_listing": True,
                    "format": "unreal-engine",
                }
            ],
            "allowed_root": str(tmp_path),
            "mode": "library_and_download",
            "free_only": True,
        },
        confirmed=True,
        dry_run=False,
    )

    assert result.state is CapabilityState.UNAVAILABLE
    assert result.details["side_effects_performed"] is False
    assert result.details["response"]["details"]["code"] == "official_provider_not_configured"


def test_worker_delegates_mutation_to_explicit_provider(tmp_path, monkeypatch):
    provider = tmp_path / "provider.py"
    provider.write_text(
        "import json,sys; request=json.load(sys.stdin); print(json.dumps({"
        "'protocol': request['protocol'], 'operation': request['operation'], "
        "'state': 'available', 'message': 'provider verified', "
        "'details': {'job_id': 'job-1', 'side_effects_performed': True}}))",
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "DCC_MCP_EPIC_FAB_PROVIDER_COMMAND",
        json.dumps([sys.executable, str(provider)]),
    )
    response = FabWorker().handle(
        {
            "protocol": HOOK_PROTOCOL,
            "operation": "fab.download.request",
            "payload": {
                "asset_id": "free-vfx",
                "project_path": str(tmp_path),
                "format": "unreal-engine",
            },
        }
    )

    assert response["state"] == CapabilityState.AVAILABLE.value
    assert response["details"]["provider_delegated"] is True
    assert response["details"]["side_effects_performed"] is True


def test_worker_completes_idempotent_sync_from_local_evidence(tmp_path, monkeypatch):
    worker = FabWorker()
    monkeypatch.setattr(
        worker.fab,
        "inspect_download_states",
        lambda *args, **kwargs: {
            "assets": [
                {
                    "asset_id": "free-vfx",
                    "state": "downloaded",
                    "owned": True,
                    "downloaded": True,
                    "format": "unreal-engine",
                }
            ]
        },
    )
    response = worker.handle(
        {
            "protocol": HOOK_PROTOCOL,
            "operation": "fab.free_assets_sync.request",
            "payload": {
                "assets": [
                    {
                        "asset_id": "free-vfx",
                        "expected_price": 0,
                        "free_listing": True,
                        "format": "unreal-engine",
                    }
                ],
                "allowed_root": str(tmp_path),
                "mode": "library_and_download",
                "free_only": True,
            },
        }
    )

    assert response["state"] == CapabilityState.AVAILABLE.value
    assert response["details"]["already_satisfied"] is True
    assert response["details"]["side_effects_performed"] is False
