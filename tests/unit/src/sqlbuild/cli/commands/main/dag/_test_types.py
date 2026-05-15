from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DagCommandTestCase:
    description: str
    expected_exit_code: int
    expected_project_name: str
    expected_node_id: str
    expected_asset_key: tuple[str, ...]
