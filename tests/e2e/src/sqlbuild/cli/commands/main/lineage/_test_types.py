from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LineageCliTestCase:
    description: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_node_ids: tuple[str, ...]
    expected_edge_ids: tuple[str, ...]
