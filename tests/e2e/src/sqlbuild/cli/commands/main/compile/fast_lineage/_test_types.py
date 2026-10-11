from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NativeFastLineageCliTestCase:
    """Every engine compiling and tracing fast lineage of one project through the CLI."""

    description: str
    files: dict[str, str]
    lineage_targets: tuple[str, ...]
    expected_lineage: dict[str, dict[str, object]]
    expected_minimum_traced_edges: int
