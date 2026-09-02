from __future__ import annotations

import importlib.util
import platform
import shutil
import sys
from typing import Any, Dict, Optional


def _version_of(command: Optional[str]) -> Optional[str]:
    if not command:
        return None
    import subprocess

    try:
        completed = subprocess.run(
            [command, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    output = (completed.stdout or completed.stderr).strip()
    return output.splitlines()[0] if output else None


def runtime_doctor() -> Dict[str, Any]:
    """Describe runtime reuse options without starting or changing any host."""

    dcc_server = shutil.which("dcc-mcp-server")
    configured_runtime = shutil.which("dcc-mcp-runtime")
    pyoxidizer = shutil.which("pyoxidizer")
    return {
        "adapter": "dcc-mcp-epic",
        "python": {
            "executable": sys.executable,
            "version": platform.python_version(),
            "mcp_sdk_available": importlib.util.find_spec("mcp") is not None,
        },
        "dcc_mcp_server": {
            "path": dcc_server,
            "version": _version_of(dcc_server),
            "kind": "rust-sidecar-or-gateway",
        },
        "shared_runtime": {
            "path": configured_runtime,
            "version": _version_of(configured_runtime),
            "kind": "pyoxidizer-bundle" if configured_runtime else None,
        },
        "pyoxidizer": {"path": pyoxidizer, "available": pyoxidizer is not None},
        "recommended_mode": (
            "reuse_dcc_mcp_sidecar"
            if dcc_server and importlib.util.find_spec("mcp") is not None
            else "use_shared_pyoxidizer_runtime"
        ),
        "unreal_embedded_python_reuse": False,
        "notes": [
            "UE embedded Python is version- and plugin-specific; do not use it "
            "as the adapter runtime",
            "Adapters should be external wheels loaded by one shared runtime",
        ],
    }
