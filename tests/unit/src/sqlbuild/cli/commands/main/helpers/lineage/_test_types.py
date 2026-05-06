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
class ColumnLineageSelectionTestCase:
    description: str
    target: str
    direction: str
    depth: int | None
    expected_resource_name: str
    expected_column_name: str
    expected_trace_ids: tuple[str, ...]
    expected_analyzed_model_names: tuple[str, ...]


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


@dataclass(frozen=True)
class ColumnLineageOutputTestCase:
    description: str
    output_format: str
    expected_output: str


@dataclass(frozen=True)
class LargeColumnLineageOutputTestCase:
    description: str
    expected_included_fragment: str
    expected_excluded_fragment: str
    expected_summary_fragment: str
    expected_json_tip_fragment: str
