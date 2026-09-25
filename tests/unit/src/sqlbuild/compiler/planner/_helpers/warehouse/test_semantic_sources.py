"""Multiple source readers share one metadata batch per database."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from unittest.mock import Mock

import duckdb
import pytest

from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.pipeline.main.project import compile_project
from sqlbuild.compiler.planner._helpers.warehouse.semantic_sources import (
    get_semantic_source_columns,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers.warehouse._test_types import (
    SemanticSourceBatchCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SemanticSourceBatchCase(
            description="two unqualified sources use one database batch",
            expected_batches=1,
            expected_sources=frozenset({"orders", "customers"}),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_multiple_missing_source_schemas_when_inspecting_then_metadata_is_batched(
    test_case: SemanticSourceBatchCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(
        tmp_path,
        {
            "sqlbuild_project.toml": 'name = "source_batch"\nadapter = "duckdb"\n',
            "sources/orders.yml": "sources:\n  - name: orders\n    table: orders\n  - name: customers\n    table: customers\n",
            "models/combined.sql": 'MODEL ();\nSELECT o.id FROM __source("orders") o JOIN __source("customers") c ON o.id = c.id',
        },
    )
    adapter: DuckDbAdapter = DuckDbAdapter()
    project: CompiledProject = compile_project(
        discovered_inputs=discover_project_inputs(project_dir=tmp_path), adapter=adapter
    )
    listings: Mock = Mock(wraps=adapter.list_relations)
    columns: Mock = Mock(wraps=adapter.get_columns_for_relations)
    monkeypatch.setattr(adapter, "list_relations", listings)
    monkeypatch.setattr(adapter, "get_columns_for_relations", columns)
    with duckdb.connect() as connection:
        connection.execute("CREATE TABLE orders(id INTEGER); CREATE TABLE customers(id INTEGER)")
        result: dict[str, tuple[ColumnInfo, ...]] = get_semantic_source_columns(
            project=project,
            adapter=adapter,
            connection=connection,
            source_read_map={source.name: source.source_entry for source in project.sources},
            columns={},
            selected_keys=frozenset(model.key for model in project.models),
        )
    assert frozenset(result) == test_case.expected_sources
    assert listings.call_count == test_case.expected_batches
    assert columns.call_count == test_case.expected_batches


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
