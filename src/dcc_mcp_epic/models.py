from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional


class CapabilityState(str, Enum):
    AVAILABLE = "available"
    READ_ONLY = "read_only"
    HUMAN_REQUIRED = "human_required"
    UNAVAILABLE = "capability_unavailable"


@dataclass(frozen=True)
class LauncherBinding:
    pid: int
    hwnd: int
    executable: Path
    version: str

    def as_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["executable"] = str(self.executable)
        return value


@dataclass(frozen=True)
class EngineInstall:
    app_name: str
    version: str
    install_location: Path
    installed: bool
    manifest_path: Path
    install_size: Optional[int] = None

    def as_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        for key in ("install_location", "manifest_path"):
            value[key] = str(value[key])
        return value


@dataclass(frozen=True)
class OperationResult:
    state: CapabilityState
    operation: str
    message: str
    details: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["state"] = self.state.value
        return value
