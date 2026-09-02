from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ...models import EngineInstall

DEFAULT_MANIFEST_ROOT = (
    Path(os.environ.get("ProgramData", r"C:\ProgramData"))
    / "Epic"
    / "EpicGamesLauncher"
    / "Data"
    / "Manifests"
)
_ENGINE_NAME = re.compile(r"^UE_\d+(?:\.\d+)?$")


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            value = json.load(handle)
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def list_engine_installs(
    manifest_root: Union[str, Path] = DEFAULT_MANIFEST_ROOT,
) -> List[EngineInstall]:
    """Read installed UE entries without modifying Epic's manifest store."""

    root = Path(manifest_root).expanduser().resolve()
    if not root.exists():
        return []
    results: List[EngineInstall] = []
    for path in sorted(root.glob("*.item")):
        data = _read_json(path)
        if not data:
            continue
        app_name = str(data.get("AppName", ""))
        if not _ENGINE_NAME.match(app_name):
            continue
        location = Path(str(data.get("InstallLocation", "")))
        results.append(
            EngineInstall(
                app_name=app_name,
                version=str(data.get("AppVersionString", "")),
                install_location=location,
                installed=not bool(data.get("bIsIncompleteInstall", False)),
                manifest_path=path,
                install_size=(
                    int(data["InstallSize"])
                    if isinstance(data.get("InstallSize"), (int, float))
                    else None
                ),
            )
        )
    return results
