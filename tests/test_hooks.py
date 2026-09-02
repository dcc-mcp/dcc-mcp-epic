import hashlib
import json
import sys

from dcc_mcp_epic.hooks import invoke_hook, load_hook_manifest, probe_hook
from dcc_mcp_epic.models import CapabilityState


def _manifest(tmp_path):
    fixture = tmp_path / "hook.py"
    fixture.write_text(
        "import json,sys; print(json.dumps({'ok': True, 'operation': "
        "json.load(sys.stdin)['operation']}))",
        encoding="utf-8",
    )
    executable = sys.executable
    digest = hashlib.sha256(open(executable, "rb").read()).hexdigest()
    path = tmp_path / "hook.json"
    path.write_text(
        json.dumps(
            {
                "protocol": "epic.hook.v1",
                "name": "test-hook",
                "version": "1.0.0",
                "command": [executable, str(fixture)],
                "operations": ["fab.download.request"],
                "requires_confirmation": ["fab.download.request"],
                "sha256": digest,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_hook_probe_and_confirmation_gate(tmp_path):
    spec = load_hook_manifest(_manifest(tmp_path))
    evidence = probe_hook(spec)
    assert evidence["sha256_verified"] is True
    result = invoke_hook(spec, "fab.download.request", {"asset_id": "a"})
    assert result.state is CapabilityState.HUMAN_REQUIRED


def test_hook_execute_uses_fixed_argv_and_json(tmp_path):
    spec = load_hook_manifest(_manifest(tmp_path))
    result = invoke_hook(
        spec,
        "fab.download.request",
        {
            "asset_id": "a",
            "project_path": str(tmp_path),
            "format": "fbx",
        },
        confirmed=True,
        dry_run=False,
    )
    assert result.state is CapabilityState.AVAILABLE
    assert result.details["response"]["ok"] is True


def test_read_only_hook_execution_does_not_claim_mutation(tmp_path):
    manifest = json.loads(_manifest(tmp_path).read_text(encoding="utf-8"))
    manifest["operations"] = ["fab.search.request"]
    manifest["requires_confirmation"] = []
    path = tmp_path / "read-only.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    spec = load_hook_manifest(path)
    result = invoke_hook(spec, "fab.search.request", {"query": "vfx"}, dry_run=False)
    assert result.state is CapabilityState.AVAILABLE
    assert result.details["side_effects_performed"] is False


def test_mutating_operation_must_declare_confirmation(tmp_path):
    manifest = json.loads(_manifest(tmp_path).read_text(encoding="utf-8"))
    manifest["operations"] = ["fab.download.request"]
    manifest["requires_confirmation"] = []
    path = tmp_path / "unsafe.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    import pytest

    with pytest.raises(ValueError, match="must require confirmation"):
        load_hook_manifest(path)


def test_hook_invoke_enforces_contract_required_fields(tmp_path):
    spec = load_hook_manifest(_manifest(tmp_path))
    result = invoke_hook(
        spec,
        "fab.download.request",
        {"asset_id": "a"},
        confirmed=True,
    )
    assert result.state is CapabilityState.UNAVAILABLE
    assert result.details["missing_fields"] == ["project_path", "format"]
