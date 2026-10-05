"""Natively rendered models must compile, build, and recompile through the real CLI."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import cast

import duckdb
import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    NativeRenderBuildTestCase,
    NativeRenderEditTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    compile_payload_without_timings,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project, run_sqb

_DIRECTORIES: tuple[str, ...] = ("marts", "marts/finance", "reporting/daily", "reporting/weekly")
_PROJECT_FILES: dict[str, str] = {
    "sqlbuild_project.toml": (
        'name = "orders"\nadapter = "duckdb"\n'
        '[vars]\nregion = "north"\n'
        "[scopes]\nenforce_placement = false\n"
        '[connection]\ndatabase = "orders.duckdb"\n'
    ),
    "constants/policy.sql": "CONSTANT (name minimum_quantity, value 2);\n",
    "enums/order_status.sql": (
        'ENUM (\n  name order_status,\n  members (\n    ACTIVE "active",\n'
        '    CLOSED "closed\'s",\n  ),\n);\n'
    ),
    "macros/formatting.py": (
        "def cents(column: str) -> str:\n"
        '    return f"CAST({column} * 100 AS BIGINT)"\n\n\n'
        "def quantity_floor(ctx) -> str:\n"
        '    return str(ctx.constants["minimum_quantity"])\n'
    ),
    "models/staging/stg_orders.sql": (
        'MODEL (description "Staged orders.", materialized table);\n'
        "SELECT 1 AS order_id, 'active' AS status, 3 AS quantity, 12.5 AS amount, "
        "'@@region' AS region\n"
        "UNION ALL SELECT 2, 'closed''s', 1, 4.0, '@@region'\n"
    ),
    **{
        f"models/{directory}/orders_{index:02d}.sql": (
            f'MODEL (description "Order view {index}.", materialized table);\n'
            "SELECT o.order_id, @cents('o.amount') AS amount_cents, "
            "@quantity_floor() AS floor_quantity\n"
            'FROM __ref("stg_orders") AS o\n'
            'WHERE o.status = @enum("order_status").ACTIVE '
            'AND o.quantity >= @const("minimum_quantity")\n'
        )
        for index, directory in enumerate(_DIRECTORIES * 2)
    },
    **{
        f"models/{directory}/totals_{index:02d}.sql": (
            f'MODEL (description "Order totals {index}.", materialized table);\n'
            "SELECT count(*) AS order_count, sum(amount_cents) AS amount_cents\n"
            f'FROM __ref("orders_{index:02d}")\n'
        )
        for index, directory in enumerate(_DIRECTORIES * 2)
    },
}


@pytest.mark.parametrize(
    "test_case",
    [
        NativeRenderBuildTestCase(
            description="macros enums constants and variables",
            expected_native_models=9,
            expected_fallback_models=8,
            expected_rows=((1, 1250, 2),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_rendered_project_when_compiling_and_building_then_native_models_materialize(
    test_case: NativeRenderBuildTestCase, tmp_path: Path
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path, project_name="orders", repo_files=_PROJECT_FILES
    )

    compiled: subprocess.CompletedProcess[str] = run_sqb(
        command=("compile", "--json"), project_dir=project_dir
    )
    built: subprocess.CompletedProcess[str] = run_sqb(
        command=("build", "--no-tests", "--no-audits"), project_dir=project_dir
    )

    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    payload: dict[str, object] = json.loads(compiled.stdout)
    timings: dict[str, int] = cast(dict[str, int], payload["compile_timings"])
    assert (timings["model_render_native"], timings["model_render_fallback"]) == (
        test_case.expected_native_models,
        test_case.expected_fallback_models,
    )
    assert built.returncode == 0, built.stdout + built.stderr
    with duckdb.connect(str(project_dir / "orders.duckdb"), read_only=True) as connection:
        rows: list[tuple[object, ...]] = connection.execute(
            "SELECT order_id, amount_cents, floor_quantity FROM orders_05"
        ).fetchall()
    assert tuple(rows) == test_case.expected_rows


@pytest.mark.parametrize(
    "test_case",
    [
        NativeRenderEditTestCase(
            description="edited macro arguments",
            edited_model="models/reporting/daily/orders_02.sql",
            old_text="@cents('o.amount')",
            new_text="@cents('o.quantity')",
        ),
        NativeRenderEditTestCase(
            description="edited enum member",
            edited_model="models/marts/orders_04.sql",
            old_text='@enum("order_status").ACTIVE',
            new_text='@enum("order_status").CLOSED',
        ),
        NativeRenderEditTestCase(
            description="edited reference",
            edited_model="models/marts/finance/totals_01.sql",
            old_text='__ref("orders_01")',
            new_text='__ref("orders_03")',
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_warm_project_when_editing_one_model_then_matches_uncached_compile(
    test_case: NativeRenderEditTestCase, tmp_path: Path
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path, project_name="orders", repo_files=_PROJECT_FILES
    )
    edited: Path = project_dir / test_case.edited_model
    cold: subprocess.CompletedProcess[str] = run_sqb(
        command=("compile", "--json"), project_dir=project_dir
    )
    warm: subprocess.CompletedProcess[str] = run_sqb(
        command=("compile", "--json"), project_dir=project_dir
    )
    _ = edited.write_text(
        edited.read_text(encoding="utf-8").replace(test_case.old_text, test_case.new_text),
        encoding="utf-8",
    )

    edit: subprocess.CompletedProcess[str] = run_sqb(
        command=("compile", "--json"), project_dir=project_dir
    )
    uncached: subprocess.CompletedProcess[str] = run_sqb(
        command=("compile", "--json", "--no-cache"), project_dir=project_dir
    )

    assert (cold.returncode, warm.returncode, edit.returncode) == (0, 0, 0), edit.stderr
    assert (
        compile_payload_without_timings(warm.stdout) == compile_payload_without_timings(cold.stdout)
    ) is test_case.expected_warm_matches_cold
    assert (
        compile_payload_without_timings(edit.stdout)
        == compile_payload_without_timings(uncached.stdout)
    ) is test_case.expected_edit_matches_uncached
    assert compile_payload_without_timings(edit.stdout) != compile_payload_without_timings(
        cold.stdout
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
