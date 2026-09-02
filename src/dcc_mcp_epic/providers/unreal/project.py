from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Union


def verify_project(project_path: Union[str, Path], expected_engine: str = "5.5") -> Dict[str, Any]:
    path = Path(project_path).expanduser().resolve()
    if path.is_dir():
        candidates = sorted(path.glob("*.uproject"))
        if len(candidates) != 1:
            return {"ok": False, "reason": "expected exactly one .uproject in directory"}
        path = candidates[0]
    if not path.exists() or path.suffix.lower() != ".uproject":
        return {"ok": False, "reason": f"uproject not found: {path}"}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return {"ok": False, "reason": f"invalid uproject: {exc}"}
    association = str(data.get("EngineAssociation", ""))
    return {
        "ok": association == expected_engine,
        "project_path": str(path),
        "engine_association": association,
        "expected_engine": expected_engine,
        "plugins": data.get("Plugins", []),
    }
