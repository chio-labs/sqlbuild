from collections import ChainMap
from collections.abc import Callable, Mapping
from copy import deepcopy
from pathlib import Path

import pytest

from sqlbuild._native import (
    RelationFixtureCompletion,
    RelationFixturePlanningContext,
    build_compiled_project,
    build_relation_fixture_completion,
    build_relation_fixture_context,
    discover_project_inputs,
)
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.types import CompiledProjectView, CompiledResourceType
from tests.integration.src.sqlbuild.compiler.planner._helpers.fixtures._test_types import (
    FixtureTypeScopeTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        FixtureTypeScopeTestCase(description="small metadata map", unrelated_relations=10),
        FixtureTypeScopeTestCase(description="large metadata map", unrelated_relations=1000),
        FixtureTypeScopeTestCase(description="very large metadata map", unrelated_relations=10000),
    ),
    ids=lambda case: case.description,
)
def test_given_unrelated_project_types_when_completing_fixture_then_eager_work_is_chain_local(
    test_case: FixtureTypeScopeTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(
        tmp_path,
        {
            "sqlbuild_project.toml": 'name = "fixture_scope"\nadapter = "duckdb"\n',
            "models/orders.sql": (
                'MODEL (description "Order facts.");\n'
                'SELECT order_id, status FROM __source("raw_orders")'
            ),
            "sources/raw_orders.yml": (
                "sources:\n  - name: raw_orders\n    description: Order input.\n"
                "    expression: SELECT 1 AS order_id, 'open' AS status\n"
                "    contract: enforced\n    columns:\n"
                "      - name: order_id\n        type: INTEGER\n        nullable: false\n"
                "      - name: status\n        type: VARCHAR\n        nullable: true\n"
            ),
        },
    )
    adapter: DuckDbAdapter = DuckDbAdapter()
    project: CompiledProjectView = build_compiled_project(
        discovered_inputs=discover_project_inputs(project_dir=tmp_path), adapter=adapter
    )
    context: RelationFixturePlanningContext = build_relation_fixture_context(project=project)
    # Model the shared project metadata supplied to every individual SQL-test plan.
    for index in range(test_case.unrelated_relations):
        context.expected_types[(CompiledResourceType.SOURCE, f"unrelated_orders_{index}")] = {
            "order_id": "INTEGER",
            "status": "VARCHAR",
        }
    before: dict[tuple[CompiledResourceType, str], dict[str, str]] = deepcopy(
        context.expected_types
    )
    fixture_key: tuple[CompiledResourceType, str] = (CompiledResourceType.SOURCE, "raw_orders")
    completed: RelationFixtureCompletion = build_relation_fixture_completion(
        project=project,
        adapter=adapter,
        request=(
            ("orders",),
            ((CompiledResourceType.SOURCE, {"raw_orders": "SELECT 1 AS order_id"}),),
        ),
        planning_context=context,
    )
    assert completed.diagnostics == ()
    assert 'CAST(NULL AS VARCHAR) AS "status"' in completed.fixture_sql_by_key[fixture_key]
    assert dict(completed.expected_types) == before
    assert list(completed.expected_types) == list(before)
    assert context.expected_types == before
    # Count eagerly materialized relation/type entries, independent of machine timing.
    eager: Mapping[tuple[CompiledResourceType, str], dict[str, str]] = getattr(
        completed.expected_types, "maps", (completed.expected_types,)
    )[0]
    assert len(eager) == test_case.expected_eager_relations
    assert sum(len(columns) for columns in eager.values()) == test_case.expected_eager_columns
    assert isinstance(completed.expected_types, ChainMap)
    assert completed.expected_types.maps[-1] is context.expected_types
    assert completed.expected_types[fixture_key] is context.expected_types[fixture_key]
    model_key: tuple[CompiledResourceType, str] = (CompiledResourceType.MODEL, "orders")
    assert completed.expected_types[model_key] is not context.expected_types[model_key]


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
