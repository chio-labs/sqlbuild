"""E2E tests for explicit, typed references in macros, Python hooks, and Python SQL."""

from __future__ import annotations

import json
import re
import subprocess
from itertools import chain
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    ExplicitReferenceAllDiagnosticsE2ETestCase,
    ExplicitReferenceBuildE2ETestCase,
    ExplicitReferenceFailureE2ETestCase,
    ExplicitReferencePythonDependencyE2ETestCase,
    ExplicitReferenceRuntimeWarningE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.build.helpers import (
    EXPLICIT_REFERENCE_HOOK_PATH,
    EXPLICIT_REFERENCE_HOOKS,
    EXPLICIT_REFERENCE_MACRO_PATH,
    EXPLICIT_REFERENCE_MACROS,
    EXPLICIT_REFERENCE_MODELS,
    explicit_reference_literal_loader,
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
_SECOND_EMITTING_MACROS: str = (
    "def customers_base():\n    return 'SELECT * FROM __ref(\"stg_customers\")'\n"
)
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


_COUNTRY_SEED_FILES: dict[str, str] = {
    "seeds/countries.yml": (
        "seeds:\n  - name: countries\n    columns:\n      - name: code\n        type: VARCHAR\n"
    ),
    "seeds/countries.csv": "code\nGB\nFR\n",
}
_SEED_TASK: str = (
    "from sqlbuild.refs import seed\n"
    "from sqlbuild.tasks import task\n\n\n"
    '@task(depends_on=seed("countries"))\n'
    "def count_countries(ctx):\n"
    '    countries = ctx.relation(seed("countries"))\n'
    "    ctx.execute_sql(\n"
    '        f"CREATE OR REPLACE TABLE country_counts AS SELECT count(*) AS n FROM {countries}"\n'
    "    )\n"
)
_MODEL_CHECK: str = (
    "from sqlbuild.checks import check\n"
    "from sqlbuild.refs import model\n\n\n"
    '@check(depends_on=model("all_orders"))\n'
    "def orders_present(ctx):\n"
    '    orders = ctx.relation(model("all_orders"))\n'
    '    count = ctx.query(f"SELECT count(*) FROM {orders}").fetchone()[0]\n'
    '    return ctx.pass_() if count else ctx.fail(message="no orders")\n'
)
_LITERAL_CHECK: str = _MODEL_CHECK.replace(
    'ctx.query(f"SELECT count(*) FROM {orders}")', 'ctx.query("SELECT count(*) FROM stg_customers")'
)
_RUNTIME_CHECK: str = _MODEL_CHECK.replace(
    '    return ctx.pass_() if count else ctx.fail(message="no orders")\n',
    '    customers = "stg_" + "customers"\n'
    '    ctx.query(f"SELECT count(*) FROM {customers}")\n'
    '    return ctx.pass_() if count else ctx.fail(message="no orders")\n',
)
_RAW_SOURCES: str = (
    "sources:\n"
    "  - name: raw_regions\n    managed: true\n    write_strategy: table\n"
    "    columns:\n      - name: id\n        type: INTEGER\n"
    "  - name: raw_customers\n    managed: true\n    write_strategy: table\n"
    "    columns:\n      - name: id\n        type: INTEGER\n"
)


@pytest.mark.parametrize(
    "test_case",
    [
        ExplicitReferencePythonDependencyE2ETestCase(
            description="task on a seed and check on a model build, order, select and check",
            select=("+task:count_countries",),
            expected_dag_edges=(
                ("seed:countries", "task:count_countries"),
                ("model:all_orders", "check:orders_present"),
            ),
            expected_checked_asset_ids=("model:all_orders",),
            expected_order_before=("countries", "count_countries"),
            expected_country_counts=((2,),),
            expected_check_row_pattern=r"check\s+orders_present\s+PASS",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_python_seed_and_model_dependencies_when_building_then_graph_selection_and_checks_hold(
    test_case: ExplicitReferencePythonDependencyE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="explicit_refs",
        repo_files=explicit_reference_project_files(
            overrides={
                **_COUNTRY_SEED_FILES,
                "python/tasks/countries.py": _SEED_TASK,
                "python/checks/orders.py": _MODEL_CHECK,
            }
        ),
    )

    dag: subprocess.CompletedProcess[str] = run_sqb(
        command=("dag", "--json"), project_dir=project_dir
    )
    selected: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", *test_case.select), project_dir=project_dir
    )
    full: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    checked: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "check"), project_dir=project_dir
    )

    assert dag.returncode == 0, dag.stdout + dag.stderr
    payload: dict[str, object] = json.loads(dag.stdout)
    edges: set[tuple[str, str]] = {(edge["from_id"], edge["to_id"]) for edge in payload["edges"]}
    assert set(test_case.expected_dag_edges) <= edges
    check_assets: dict[str, tuple[str, ...]] = {
        check["id"]: tuple(check["checked_asset_ids"]) for check in payload["checks"]
    }
    assert check_assets["check:orders_present"] == test_case.expected_checked_asset_ids
    assert selected.returncode == 0, selected.stdout + selected.stderr
    first, second = test_case.expected_order_before
    assert selected.stdout.index(f" {first} ") < selected.stdout.index(f" {second} ")
    assert " all_orders " not in selected.stdout
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb", sql="SELECT n FROM country_counts"
    ) == list(test_case.expected_country_counts)
    assert full.returncode == 0, full.stdout + full.stderr
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert re.search(test_case.expected_check_row_pattern, full.stdout), full.stdout
    assert re.search(test_case.expected_check_row_pattern, checked.stdout), checked.stdout


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
        ExplicitReferenceFailureE2ETestCase(
            description="check literal SQL naming an undeclared model fails compile",
            overrides={"python/checks/orders.py": _LITERAL_CHECK},
            command=("--no-color", "compile"),
            expected_exit_code=1,
            expected_output_fragments=(
                "error[P008]: check:orders_present names model:stg_customers as 'stg_customers'",
                "--> python/checks/orders.py:8",
                'declare it with depends_on=model("stg_customers")',
            ),
        ),
        ExplicitReferenceFailureE2ETestCase(
            description="loader literal SQL naming a source fails compile with ctx.source help",
            overrides={
                "sources/raw.yml": _RAW_SOURCES,
                "python/loaders/raw.py": explicit_reference_literal_loader(table="raw_regions"),
            },
            command=("--no-color", "compile"),
            expected_exit_code=1,
            expected_output_fragments=(
                "error[P008]: loader:raw_customers names source:raw_regions as 'raw_regions'",
                'use ctx.source("raw_regions") instead of the relation name',
            ),
        ),
        ExplicitReferenceFailureE2ETestCase(
            description="loader literal SQL naming a model fails compile",
            overrides={
                "sources/raw.yml": _RAW_SOURCES,
                "python/loaders/raw.py": explicit_reference_literal_loader(table="stg_customers"),
            },
            command=("--no-color", "compile"),
            expected_exit_code=1,
            expected_output_fragments=(
                "error[P008]: loader:raw_customers names model:stg_customers as 'stg_customers'",
                "loaders run before models and seeds and cannot read them",
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


@pytest.mark.parametrize(
    "test_case",
    [
        ExplicitReferenceRuntimeWarningE2ETestCase(
            description="check naming an undeclared model at run time warns and passes",
            overrides={"python/checks/orders.py": _RUNTIME_CHECK},
            enforce_explicit=True,
            expected_exit_code=0,
            expected_warning_fragments=(
                "[P008] check 'orders_present' named model:stg_customers as 'stg_customers'",
            ),
            expected_final_line_prefix="",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_check_runtime_hard_coded_relation_when_building_then_it_warns_without_failing(
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

    machine: subprocess.CompletedProcess[str] = run_sqb(
        command=("build", "--json"), project_dir=project_dir
    )

    assert machine.returncode == test_case.expected_exit_code, machine.stdout + machine.stderr
    assert all(fragment in machine.stderr for fragment in test_case.expected_warning_fragments)
    stored: list[str] = list(
        chain.from_iterable(
            check.get("warnings") or () for check in json.loads(machine.stdout)["checks"]
        )
    )
    assert len(stored) == len(test_case.expected_warning_fragments)
    assert all(
        fragment in warning
        for warning, fragment in zip(stored, test_case.expected_warning_fragments, strict=True)
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ExplicitReferenceAllDiagnosticsE2ETestCase(
            description="two ref-emitting macros and a hard-coded task name all report at once",
            overrides={
                EXPLICIT_REFERENCE_MACRO_PATH: _EMITTING_MACROS,
                "models/sales/_sqlbuild/_macros/customers.py": _SECOND_EMITTING_MACROS,
                f"{EXPLICIT_REFERENCE_MODELS}/hidden.sql": _EMITTING_MODEL,
                f"{EXPLICIT_REFERENCE_MODELS}/hidden_customers.sql": (
                    "MODEL (materialized table);\n@customers_base()\n"
                ),
                "python/tasks/export.py": _LITERAL_TASK,
            },
            expected_output_fragments=(
                "error[P006]: model:hidden depends on model:stg_orders_eu through macro "
                "orders_base()",
                "error[P006]: model:hidden_customers depends on model:stg_customers through macro "
                "customers_base()",
                "error[P008]: task:export_orders names model:stg_customers as 'stg_customers'",
                "3 errors",
            ),
            expected_json_diagnostics=(
                ("P006", "model:hidden depends on model:stg_orders_eu through macro orders_base()"),
                (
                    "P006",
                    "model:hidden_customers depends on model:stg_customers through macro "
                    "customers_base()",
                ),
                (
                    "P008",
                    "task:export_orders names model:stg_customers as 'stg_customers' in SQL "
                    "passed to ctx.query()",
                ),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_several_implicit_references_when_compiling_then_one_compile_reports_all(
    test_case: ExplicitReferenceAllDiagnosticsE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="explicit_refs",
        repo_files=explicit_reference_project_files(overrides=test_case.overrides),
    )

    text: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "compile"), project_dir=project_dir
    )
    machine: subprocess.CompletedProcess[str] = run_sqb(
        command=("compile", "--json", "--no-cache"), project_dir=project_dir
    )

    assert text.returncode == 1, text.stdout + text.stderr
    output: str = text.stdout + text.stderr
    assert all(fragment in output for fragment in test_case.expected_output_fragments), output
    assert machine.returncode == 1, machine.stdout + machine.stderr
    payload: dict[str, object] = json.loads(machine.stdout)
    assert payload["has_errors"] is True
    assert (
        tuple((item["code"], item["message"]) for item in payload["diagnostics"])
        == test_case.expected_json_diagnostics
    )
