from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DagArtifactTestCase:
    description: str
    expected_node_ids: tuple[str, ...]
    expected_edge_pairs: tuple[tuple[str, str], ...]
    expected_check_ids: tuple[str, ...]
    expected_function_asset_key: tuple[str, ...]
    expected_source_asset_key: tuple[str, ...]


@dataclass(frozen=True)
class DagJsonTestCase:
    description: str
    expected_version: int
    expected_project_name: str
    expected_node_count: int
    expected_absent_fragments: tuple[str, ...]
