import json
import subprocess

from dcc_mcp_epic.cua_preflight import preflight_launcher


def test_preflight_runs_only_read_only_project_route_and_binds_exact_window(tmp_path, monkeypatch):
    executable = tmp_path / "EpicGamesLauncher.exe"
    executable.write_bytes(b"launcher")
    cua = tmp_path / "dcc-cua.exe"
    cua.write_bytes(b"cua")
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((list(argv), kwargs))
        suffix = list(argv[1:])
        if suffix == ["--version"]:
            return subprocess.CompletedProcess(argv, 0, "dcc-cua 1.7.1\n", "")
        if suffix == ["ping"]:
            return subprocess.CompletedProcess(
                argv, 0, json.dumps({"type": "pong", "host_version": "1.7.1"}), ""
            )
        if suffix == ["doctor", "--route", "visual"]:
            return subprocess.CompletedProcess(
                argv,
                0,
                json.dumps(
                    {
                        "ready": True,
                        "routes": {"visual": {"ready": True}},
                        "interactive_desktop": {
                            "observation_ready": True,
                            "input_ready": True,
                        },
                    }
                ),
                "",
            )
        if suffix == ["list", "--pid", "123", "--window-id", "456"]:
            return subprocess.CompletedProcess(
                argv,
                0,
                json.dumps(
                    [
                        {
                            "pid": 123,
                            "window_id": 456,
                            "app_name": "EpicGamesLauncher.exe",
                            "is_on_screen": True,
                            "minimized": False,
                        }
                    ]
                ),
                "",
            )
        raise AssertionError(f"unexpected command: {suffix}")

    monkeypatch.setattr("dcc_mcp_epic.cua_preflight.subprocess.run", fake_run)
    report = preflight_launcher(
        123,
        456,
        executable,
        cua_command=[str(cua)],
    )

    assert report["status"] == "ready"
    assert report["provider"] == "dcc-cua"
    assert report["runtime"] == "dcc-cua 1.7.1"
    assert report["target"] == {
        "pid": 123,
        "hwnd": 456,
        "executable": str(executable.resolve()),
    }
    assert report["window"]["window_id"] == 456
    assert len(calls) == 4
    assert all(kwargs["shell"] is False for _, kwargs in calls)


def test_preflight_reports_disconnected_session_without_claiming_ready(tmp_path, monkeypatch):
    executable = tmp_path / "EpicGamesLauncher.exe"
    executable.write_bytes(b"launcher")
    cua = tmp_path / "dcc-cua.exe"
    cua.write_bytes(b"cua")

    def fake_run(argv, **kwargs):
        suffix = list(argv[1:])
        if suffix == ["--version"]:
            return subprocess.CompletedProcess(argv, 0, "dcc-cua 1.7.1\n", "")
        if suffix == ["ping"]:
            return subprocess.CompletedProcess(argv, 0, '{"type":"pong"}', "")
        if suffix == ["doctor", "--route", "visual"]:
            return subprocess.CompletedProcess(
                argv,
                1,
                json.dumps(
                        {
                            "ready": False,
                            "routes": {"visual": {"ready": False}},
                            "checks": {
                                "interactive_desktop": {
                                    "code": "interactive_session_not_active",
                                    "session_state": "disconnected",
                                    "observation_ready": False,
                                }
                            },
                        }
                ),
                "",
            )
        if suffix == ["list", "--pid", "123", "--window-id", "456"]:
            return subprocess.CompletedProcess(argv, 0, "[]", "")
        raise AssertionError(f"unexpected command: {suffix}")

    monkeypatch.setattr("dcc_mcp_epic.cua_preflight.subprocess.run", fake_run)
    report = preflight_launcher(123, 456, executable, cua_command=[str(cua)])

    assert report["status"] == "blocked"
    assert report["ready"] is False
    assert report["interactive_desktop"]["code"] == "interactive_session_not_active"
    assert report["next_action"] == "reconnect the bound Windows interactive session"


def test_preflight_fails_closed_for_window_identity_mismatch(tmp_path, monkeypatch):
    executable = tmp_path / "EpicGamesLauncher.exe"
    executable.write_bytes(b"launcher")
    cua = tmp_path / "dcc-cua.exe"
    cua.write_bytes(b"cua")

    def fake_run(argv, **kwargs):
        suffix = list(argv[1:])
        if suffix == ["--version"]:
            return subprocess.CompletedProcess(argv, 0, "dcc-cua 1.7.1\n", "")
        if suffix == ["ping"]:
            return subprocess.CompletedProcess(argv, 0, '{"type":"pong"}', "")
        if suffix == ["doctor", "--route", "visual"]:
            return subprocess.CompletedProcess(argv, 0, '{"ready":true}', "")
        if suffix == ["list", "--pid", "123", "--window-id", "456"]:
            return subprocess.CompletedProcess(
                argv,
                0,
                json.dumps([{"pid": 999, "window_id": 456}]),
                "",
            )
        raise AssertionError(f"unexpected command: {suffix}")

    monkeypatch.setattr("dcc_mcp_epic.cua_preflight.subprocess.run", fake_run)
    report = preflight_launcher(123, 456, executable, cua_command=[str(cua)])

    assert report["status"] == "blocked"
    assert report["ready"] is False
    assert report["error"]["code"] == "exact_window_not_found"
