"""Native layering policy models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NativeLayers:
    """Declared crate order and the crates that bound PyO3 and polyglot."""

    order: tuple[str, ...]
    python_boundary: str
    polyglot_floor: str
