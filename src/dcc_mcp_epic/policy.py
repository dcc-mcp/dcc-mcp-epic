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


def require_free_listing(expected_price: Union[int, float], free_listing: bool) -> None:
    """Require an explicit free-price assertion before account mutations.

    Adding an item to an Epic/Fab library is the operation that establishes
    ownership, so ``require_free_asset`` cannot be reused here.  Callers must
    provide both a zero expected price and an explicit ``free_listing`` flag;
    the user-owned hook remains responsible for obtaining fresh listing
    evidence before executing the account-side action.
    """

    if expected_price != 0:
        raise ValueError("free-only policy rejected an asset with non-zero expected price")
    if free_listing is not True:
        raise ValueError("free listing has not been explicitly verified")
