"""E2E: layered, templated and validated model config builds the same on every compiler engine.

The preview engine builds model config (path defaults, templates, storage policies) and checks the
model validators natively; a validator rejection re-runs Python for the exact error. Every engine
must build the same relations and report the same validator errors.
"""

from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    ModelConfigEnginesBuildE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    execute_duckdb,
    prepare_inline_project,
    query_duckdb,
    run_sqb,
)

_ENGINE_ENV_VAR: str = "SQLBUILD_COMPILER_ENGINE"
_MART_SCHEMA_ENV_VAR: str = "SQB_MART_SCHEMA"
_INCREMENTAL_MODEL: str = "models/marts/orders_incremental.sql"
_SNAPSHOT_MODEL: str = "models/marts/order_history.sql"
_PROJECT_FILES: dict[str, str] = {
    "sqlbuild_project.toml": (
        'name = "orders"\nadapter = "duckdb"\ndefault_target = "dev"\n\n'
        '[connections.local]\ndatabase = "orders.duckdb"\n\n'
        '[targets.dev]\nconnection = "local"\n\n'
        '[defaults]\nmaterialized = "view"\ntags = ["core"]\n\n'
        '[path_defaults.marts]\nmaterialized = "table"\n'
        'schema = "${coalesce(ENV:SQB_MART_SCHEMA, \'marts\')}"\ntags = ["marts"]\n\n'
        '[path_defaults."staging/*"]\nschema = "staging"\n'
    ),
    "models/staging/stg_orders.sql": (
        'MODEL (description "Staged orders.");\n\n'
        "SELECT * FROM (VALUES (1, 10, 'placed'), (2, 20, 'shipped'))"
        " AS t(order_id, amount, status)\n"
    ),
    "models/marts/order_totals.sql": (
        'MODEL (\n  description "Order totals for ${CTX:run.target}.",\n'
        '  alias "${CTX:model.name}_v2",\n  tags ["daily"],\n);\n\n'
        'SELECT status, SUM(amount) AS total_amount\nFROM __ref("stg_orders")\nGROUP BY status\n'
    ),
    _INCREMENTAL_MODEL: (
        'MODEL (\n  description "Orders loaded incrementally.",\n'
        "  materialized incremental,\n  incremental_strategy delete_insert,\n"
        '  cursor order_id,\n  cursor_type integer,\n  cursor_start "0",\n  cursor_end 100,\n'
        "  unique_key [order_id],\n);\n\n"
        'SELECT order_id, amount\nFROM __ref("stg_orders")\n'
        "WHERE order_id >= __cursor_start() AND order_id < __cursor_end()\n"
    ),
    _SNAPSHOT_MODEL: (
        'MODEL (\n  description "Order status history.",\n  materialized snapshot,\n'
        "  unique_key [order_id],\n  snapshot_strategy check,\n  check_columns [status],\n);\n\n"
        'SELECT order_id, status\nFROM __ref("stg_orders")\n'
    ),
}
_REVERSED_CURSOR_BOUNDS: dict[str, str] = {
    _INCREMENTAL_MODEL: _PROJECT_FILES[_INCREMENTAL_MODEL].replace(
        "cursor_end 100", "cursor_end -5"
    )
}
_SNAPSHOT_WITHOUT_KEY: dict[str, str] = {
    _SNAPSHOT_MODEL: _PROJECT_FILES[_SNAPSHOT_MODEL].replace("  unique_key [order_id],\n", "")
}
_BUILT_RELATIONS: tuple[tuple[str, str], ...] = (
    ("analytics", "order_history"),
    ("analytics", "order_totals_v2"),
    ("analytics", "orders_incremental"),
    ("staging", "stg_orders"),
)
_PASSING_FRAGMENTS: tuple[str, ...] = ("PASS=4  WARN=0  FAIL=0",)
_REVERSED_BOUNDS_FRAGMENTS: tuple[str, ...] = (
    "error[P001]: model 'orders_incremental': cursor_start must be before exclusive cursor_end",
)
_SNAPSHOT_WITHOUT_KEY_FRAGMENTS: tuple[str, ...] = (
    "error[P001]: model 'order_history': snapshot materialization requires unique_key",
)


@pytest.mark.parametrize(
    "test_case",
    [
        ModelConfigEnginesBuildE2ETestCase(
            description="layered and templated config builds on python",
            engine="python",
            overrides={},
            expected_exit_code=0,
            expected_output_fragments=_PASSING_FRAGMENTS,
            expected_relations=_BUILT_RELATIONS,
        ),
        ModelConfigEnginesBuildE2ETestCase(
            description="reversed cursor bounds are the Python error on python",
            engine="python",
            overrides=_REVERSED_CURSOR_BOUNDS,
            expected_exit_code=1,
            expected_output_fragments=_REVERSED_BOUNDS_FRAGMENTS,
            expected_relations=(),
        ),
        ModelConfigEnginesBuildE2ETestCase(
            description="a snapshot without a unique key is the Python error on python",
            engine="python",
            overrides=_SNAPSHOT_WITHOUT_KEY,
            expected_exit_code=1,
            expected_output_fragments=_SNAPSHOT_WITHOUT_KEY_FRAGMENTS,
            expected_relations=(),
        ),
        ModelConfigEnginesBuildE2ETestCase(
            description="layered and templated config builds on native",
            engine="native",
            overrides={},
            expected_exit_code=0,
            expected_output_fragments=_PASSING_FRAGMENTS,
            expected_relations=_BUILT_RELATIONS,
        ),
        ModelConfigEnginesBuildE2ETestCase(
            description="reversed cursor bounds are the Python error on native",
            engine="native",
            overrides=_REVERSED_CURSOR_BOUNDS,
            expected_exit_code=1,
            expected_output_fragments=_REVERSED_BOUNDS_FRAGMENTS,
            expected_relations=(),
        ),
        ModelConfigEnginesBuildE2ETestCase(
            description="a snapshot without a unique key is the Python error on native",
            engine="native",
            overrides=_SNAPSHOT_WITHOUT_KEY,
            expected_exit_code=1,
            expected_output_fragments=_SNAPSHOT_WITHOUT_KEY_FRAGMENTS,
            expected_relations=(),
        ),
        ModelConfigEnginesBuildE2ETestCase(
            description="layered and templated config builds on native-preview",
            engine="native-preview",
            overrides={},
            expected_exit_code=0,
            expected_output_fragments=_PASSING_FRAGMENTS,
            expected_relations=_BUILT_RELATIONS,
        ),
        ModelConfigEnginesBuildE2ETestCase(
            description="reversed cursor bounds are the Python error on native-preview",
            engine="native-preview",
            overrides=_REVERSED_CURSOR_BOUNDS,
            expected_exit_code=1,
            expected_output_fragments=_REVERSED_BOUNDS_FRAGMENTS,
            expected_relations=(),
        ),
        ModelConfigEnginesBuildE2ETestCase(
            description="a snapshot without a unique key is the Python error on native-preview",
            engine="native-preview",
            overrides=_SNAPSHOT_WITHOUT_KEY,
            expected_exit_code=1,
            expected_output_fragments=_SNAPSHOT_WITHOUT_KEY_FRAGMENTS,
            expected_relations=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_layered_model_config_when_building_on_each_engine_then_results_match(
    test_case: ModelConfigEnginesBuildE2ETestCase, tmp_path: Path
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="orders",
        repo_files={**_PROJECT_FILES, **test_case.overrides},
    )

    result: CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
        env={_ENGINE_ENV_VAR: test_case.engine, _MART_SCHEMA_ENV_VAR: "analytics"},
    )
    output: str = result.stdout + result.stderr
    execute_duckdb(db_path=project_dir / "orders.duckdb", sql="SELECT 1")
    relations: list[tuple[Any, ...]] = query_duckdb(
        db_path=project_dir / "orders.duckdb",
        sql=(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_schema IN ('analytics', 'staging') "
            "AND NOT starts_with(table_name, '_sqlbuild') ORDER BY 1, 2"
        ),
    )

    assert result.returncode == test_case.expected_exit_code, output
    assert [fragment in output for fragment in test_case.expected_output_fragments] == [True] * len(
        test_case.expected_output_fragments
    ), output
    assert tuple(relations) == test_case.expected_relations


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
