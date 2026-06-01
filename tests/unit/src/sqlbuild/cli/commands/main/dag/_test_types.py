from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DagCommandTestCase:
    description: str
    expected_exit_code: int
    expected_project_name: str
    expected_node_id: str
    expected_asset_key: tuple[str, ...]


@dataclass(frozen=True)
class PythonDagCommandTestCase:
    description: str
    expected_exit_code: int
    expected_task_id: str
    expected_task_tags: list[str]
    expected_task_group: str
    expected_task_meta: dict[str, object]
    expected_loader_id: str
    expected_loader_columns: list[dict[str, object]]
    expected_asset_id: str
    expected_asset_key: list[str]
    expected_asset_description: str
    expected_asset_group: str
    expected_asset_materialization_type: str
    expected_asset_columns: list[dict[str, object]]
    expected_asset_column_lineage: dict[str, list[dict[str, object]]]
    expected_check_id: str
    expected_check_group: str
    expected_edges: set[tuple[str, str]]
    expected_check: dict[str, object]
    expected_loader_check_id: str
    expected_loader_check: dict[str, object]
