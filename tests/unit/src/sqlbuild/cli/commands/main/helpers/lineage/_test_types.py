from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LineageSelectionTestCase:
    description: str
    target: str
    direction: str
    depth: int | None
    expected_node_ids: tuple[str, ...]
    expected_edge_ids: tuple[str, ...]


@dataclass(frozen=True)
class LineageSelectorDepthErrorTestCase:
    description: str
    select: tuple[str, ...]
    expected_error_fragment: str


@dataclass(frozen=True)
class LineageOutputTestCase:
    description: str
    output_format: str
    expected_output: str
