"""E2E tests for explicit, typed references in macros, Python hooks, and Python SQL."""

from __future__ import annotations

import json
import subprocess
from itertools import chain
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    ExplicitReferenceBuildE2ETestCase,
    ExplicitReferenceFailureE2ETestCase,
    ExplicitReferenceRuntimeWarningE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.build.helpers import (
    EXPLICIT_REFERENCE_HOOK_PATH,
    EXPLICIT_REFERENCE_HOOKS,
    EXPLICIT_REFERENCE_MACRO_PATH,
    EXPLICIT_REFERENCE_MACROS,
    EXPLICIT_REFERENCE_MODELS,
    explicit_reference_project_files,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_inline_project,
    query_duckdb,
    run_sqb,
)

_EMITTING_MACROS: str = (
    EXPLICIT_REFERENCE_MACROS
    + "\n\ndef orders_base():\n    return 'SELECT * FROM __ref(\"stg_orders_eu\")'\n"
)
_EMITTING_MODEL: str = "MODEL (materialized table);\n@orders_base()\n"
_UNDECLARED_HOOKS: str = EXPLICIT_REFERENCE_HOOKS + '    ctx.relation(model("all_orders"))\n'
_LITERAL_TASK: str = (
    "from sqlbuild.refs import model\n"
    "from sqlbuild.tasks import task\n\n\n"
    '@task(depends_on=model("all_orders"))\n'
    "def export_orders(ctx):\n"
    '    ctx.query("SELECT count(*) FROM stg_customers")\n'
)
_RUNTIME_TASK: str = (
    "from sqlbuild.refs import model\n"
    "from sqlbuild.tasks import task\n\n\n"
    '@task(depends_on=model("all_orders"))\n'
    "def export_orders(ctx):\n"
    '    orders = ctx.relation(model("all_orders"))\n'
    '    ctx.query(f"SELECT count(*) FROM {orders}")\n'
    '    customers = "stg_" + "customers"\n'
    '    ctx.query(f"SELECT count(*) FROM {customers}")\n'
)


@pytest.mark.parametrize(
    "test_case",
    [
        ExplicitReferenceBuildE2ETestCase(
            description="typed macro references record lineage and hook reads order the build",
            overrides={},
            expected_exit_code=0,
            expected_dag_edges=(
                ("model:stg_orders_eu", "model:all_orders"),
                ("model:stg_orders_us", "model:all_orders"),
            ),
            expected_customer_counts=((1,),),
            expected_order_before=("stg_customers", "orders_summary"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_typed_macro_references_and_hook_reads_when_building_then_graph_and_order_hold(
    test_case: ExplicitReferenceBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="explicit_refs",
        repo_files=explicit_reference_project_files(overrides=test_case.overrides),
    )

    dag: subprocess.CompletedProcess[str] = run_sqb(
        command=("dag", "--json"), project_dir=project_dir
    )
    build: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--concurrency", "4"), project_dir=project_dir
    )

    assert dag.returncode == 0, dag.stdout + dag.stderr
    edges: set[tuple[str, str]] = {
        (edge["from_id"], edge["to_id"]) for edge in json.loads(dag.stdout)["edges"]
    }
    assert set(test_case.expected_dag_edges) <= edges
    assert build.returncode == test_case.expected_exit_code, build.stdout + build.stderr
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb", sql="SELECT n FROM customer_counts"
    ) == list(test_case.expected_customer_counts)
    first, second = test_case.expected_order_before
    assert build.stdout.index(f" {first} ") < build.stdout.index(f" {second} ")


@pytest.mark.parametrize(
    "test_case",
    [
        ExplicitReferenceFailureE2ETestCase(
            description="macro emitting a reference fails compile",
            overrides={
                EXPLICIT_REFERENCE_MACRO_PATH: _EMITTING_MACROS,
                f"{EXPLICIT_REFERENCE_MODELS}/hidden.sql": _EMITTING_MODEL,
            },
            command=("--no-color", "compile"),
            expected_exit_code=1,
            expected_output_fragments=(
                "error[P006]: model:hidden depends on model:stg_orders_eu through macro "
                "orders_base()",
                "--> models/sales/_sqlbuild/_macros/unions.py",
                '@orders_base(__ref("stg_orders_eu"))',
                "[references] enforce_explicit = false",
            ),
        ),
        ExplicitReferenceFailureE2ETestCase(
            description="hook resolving an undeclared relation fails the build",
            overrides={EXPLICIT_REFERENCE_HOOK_PATH: _UNDECLARED_HOOKS},
            command=("--no-color", "build"),
            expected_exit_code=1,
            expected_output_fragments=(
                "SQL relation ref 'all_orders' must be declared in @hook(reads=...)",
            ),
        ),
        ExplicitReferenceFailureE2ETestCase(
            description="literal SQL naming a project relation fails compile",
            overrides={"python/tasks/export.py": _LITERAL_TASK},
            command=("--no-color", "compile"),
            expected_exit_code=1,
            expected_output_fragments=(
                "error[P008]: task:export_orders names model:stg_customers as 'stg_customers'",
                "--> python/tasks/export.py:7",
                "[references] enforce_explicit = false",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_implicit_reference_when_running_command_then_it_fails_with_guidance(
    test_case: ExplicitReferenceFailureE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="explicit_refs",
        repo_files=explicit_reference_project_files(overrides=test_case.overrides),
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command, project_dir=project_dir
    )

    output: str = result.stdout + result.stderr
    assert result.returncode == test_case.expected_exit_code, output
    assert all(fragment in output for fragment in test_case.expected_output_fragments)


@pytest.mark.parametrize(
    "test_case",
    [
        ExplicitReferenceRuntimeWarningE2ETestCase(
            description="run-time hard-coded name warns while the build succeeds",
            overrides={"python/tasks/export.py": _RUNTIME_TASK},
            enforce_explicit=True,
            expected_exit_code=0,
            expected_warning_fragments=(
                "[P008] task 'export_orders' named model:stg_customers as 'stg_customers'",
            ),
            expected_final_line_prefix="\u2713 Completed with warnings",
        ),
        ExplicitReferenceRuntimeWarningE2ETestCase(
            description="enforcement disabled allows every implicit reference",
            overrides={
                "python/tasks/export.py": _RUNTIME_TASK,
                EXPLICIT_REFERENCE_MACRO_PATH: _EMITTING_MACROS,
                f"{EXPLICIT_REFERENCE_MODELS}/hidden.sql": _EMITTING_MODEL,
                "python/tasks/literal.py": _LITERAL_TASK.replace(
                    "export_orders", "count_customers"
                ),
            },
            enforce_explicit=False,
            expected_exit_code=0,
            expected_warning_fragments=(),
            expected_final_line_prefix="\u2713 Completed successfully",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_runtime_hard_coded_relation_when_building_then_it_warns_without_failing(
    test_case: ExplicitReferenceRuntimeWarningE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="explicit_refs",
        repo_files=explicit_reference_project_files(
            overrides=test_case.overrides, enforce_explicit=test_case.enforce_explicit
        ),
    )

    text: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    machine: subprocess.CompletedProcess[str] = run_sqb(
        command=("build", "--json"), project_dir=project_dir
    )

    assert text.returncode == test_case.expected_exit_code, text.stdout + text.stderr
    assert machine.returncode == test_case.expected_exit_code, machine.stdout + machine.stderr
    assert all(fragment in text.stdout for fragment in test_case.expected_warning_fragments)
    assert text.stdout.strip().splitlines()[-1].startswith(test_case.expected_final_line_prefix)
    stored: list[str] = list(
        chain.from_iterable(
            asset.get("warnings") or () for asset in json.loads(machine.stdout)["assets"]
        )
    )
    assert len(stored) == len(test_case.expected_warning_fragments)
    assert all(
        fragment in warning
        for warning, fragment in zip(stored, test_case.expected_warning_fragments, strict=True)
    )
