from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DagArtifactTestCase:
    description: str
    expected_node_ids: tuple[str, ...]
    expected_edge_pairs: tuple[tuple[str, str], ...]
    expected_check_ids: tuple[str, ...]
    expected_function_asset_key: tuple[str, ...]
    expected_seed_asset_key: tuple[str, ...]
    expected_source_asset_key: tuple[str, ...]
    expected_loader_asset_key: tuple[str, ...]


@dataclass(frozen=True)
class DagResourceNamespaceTestCase:
    description: str
    expected_seed_namespace: tuple[str, str, str, str]
    expected_function_namespace: tuple[str, str, str, str]


@dataclass(frozen=True)
class DagJsonTestCase:
    description: str
    expected_version: int
    expected_project_name: str
    expected_node_count: int
    expected_absent_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DagProducedKindsTestCase:
    description: str
    expected_kinds: frozenset[str]
    expected_enum_values: frozenset[str]


@dataclass(frozen=True)
class DagLoaderDestinationTestCase:
    description: str
    destination: str
    expected_target_parts: tuple[str, str, str]
