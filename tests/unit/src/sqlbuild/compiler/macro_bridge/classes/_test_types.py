from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeepNestingScanTestCase:
    """Macro calls nested `depth` levels deep and the scan the bridge must return quickly."""

    description: str
    depth: int
    expected_tree_names: tuple[tuple[str, ...], ...]
    expected_max_seconds: float
