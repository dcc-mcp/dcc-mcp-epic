from dcc_mcp_epic.runtime import runtime_doctor


def test_runtime_doctor_has_explicit_embedded_python_boundary():
    report = runtime_doctor()
    assert report["unreal_embedded_python_reuse"] is False
    assert report["recommended_mode"] in {
        "reuse_dcc_mcp_sidecar",
        "use_shared_pyoxidizer_runtime",
    }
