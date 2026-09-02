from __future__ import annotations

from pathlib import Path
from typing import Union


def resolve_allowed_project(path: Union[str, Path], allowed_root: Union[str, Path]) -> Path:
    """Resolve a project path and reject traversal outside the approved root."""

    root = Path(allowed_root).expanduser().resolve()
    candidate = Path(path).expanduser().resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"project path is outside allowed root: {candidate}") from exc
    return candidate


def require_free_asset(expected_price: Union[int, float], owned: bool) -> None:
    if expected_price != 0:
        raise ValueError("free-only policy rejected an asset with non-zero expected price")
    if not owned:
        raise ValueError("asset ownership has not been verified")
