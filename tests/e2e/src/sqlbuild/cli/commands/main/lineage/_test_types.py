from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LineageCliTestCase:
    description: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_node_ids: tuple[str, ...]
    expected_edge_ids: tuple[str, ...]


@dataclass(frozen=True)
class LineageCacheCliTestCase:
    description: str
    command: tuple[str, ...]
    expected_node_id: str


@dataclass(frozen=True)
class ColumnLineageCacheCliTestCase:
    description: str
    command: tuple[str, ...]
    expected_source_resource: str


@dataclass(frozen=True)
class LineageErrorCliTestCase:
    description: str
    command: tuple[str, ...]
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DiamondLineageTreeCliTestCase:
    description: str
    command: tuple[str, ...]
    expected_expanded_names: tuple[str, ...]
    expected_max_lines: int


@dataclass(frozen=True)
class SharedSelectorCliTestCase:
    description: str
    selector: str
    expected_node_ids: tuple[str, ...]
    expected_selected_models: int
    expected_selected_functions: int


@dataclass(frozen=True)
class SharedSelectorErrorCliTestCase:
    description: str
    selector: str
    expected_fragment: str
