"""Literal SQL in tasks, assets, and hooks must not hard-code project relation names."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from sqlbuild.compiler.compile.models import CompiledProject
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    PythonSqlReferenceAllowedTestCase,
    PythonSqlReferenceErrorTestCase,
)
from tests.unit.src.sqlbuild.compiler.compile._helpers.helpers import (
    compile_and_assemble,
    gate_model,
    python_hook_source,
    python_task_source,
)

_PROJECT_FILE: str = """
name = "demo"
adapter = "duckdb"

[settings]
sql_analysis = false
sql_validation = false
"""
_DISABLED_PROJECT_FILE: str = _PROJECT_FILE + "\n[references]\nenforce_explicit = false\n"
_HOOK_PATH: str = "models/marts/_sqlbuild/_hooks/python/lookups.py"
_TASK_PATH: str = "python/tasks/export.py"
_HOOKED_HEADER: str = 'MODEL (post_hooks [python("refresh_lookup")]);'
_MODELS: dict[str, str] = {
    "models/marts/customers.sql": gate_model(sql="SELECT 1 AS customer_id"),
    "models/marts/orders.sql": gate_model(sql="SELECT 1 AS order_id", header=_HOOKED_HEADER),
}
_COUNTRY_SEED: dict[str, str] = {
    "seeds/country_codes.yml": (
        "seeds:\n  - name: country_codes\n    columns:\n      - name: code\n        type: VARCHAR\n"
    ),
    "seeds/country_codes.csv": "code\nGB\n",
}


@pytest.mark.parametrize(
    "test_case",
    (
        PythonSqlReferenceErrorTestCase(
            description="task literal SQL naming a model",
            files={
                **_MODELS,
                _HOOK_PATH: python_hook_source(),
                _TASK_PATH: python_task_source(
                    body='    ctx.query("SELECT count(*) FROM customers")\n'
                ),
            },
            expected_error_fragments=(
                "[P008]",
                "task:export_orders names model:customers as 'customers' in SQL passed to "
                "ctx.query()",
                "python/tasks/export.py:7",
                'depends_on=model("customers")',
                "[references] enforce_explicit = false",
            ),
        ),
        PythonSqlReferenceErrorTestCase(
            description="hook f-string with a literal seed table part",
            files={
                **_MODELS,
                **_COUNTRY_SEED,
                _HOOK_PATH: python_hook_source(
                    body=(
                        "    limit = 10\n"
                        '    ctx.execute_sql(f"SELECT * FROM country_codes LIMIT {limit}")\n'
                    )
                ),
            },
            expected_error_fragments=(
                "hook:refresh_lookup names seed:country_codes",
                "ctx.execute_sql()",
                '@hook(reads=seed("country_codes"))',
            ),
        ),
        PythonSqlReferenceErrorTestCase(
            description="hook literal SQL naming a schema-qualified model",
            files={
                **_MODELS,
                _HOOK_PATH: python_hook_source(
                    body='    ctx.query("SELECT * FROM main.customers")\n'
                ),
            },
            expected_error_fragments=("names model:customers as 'main.customers'",),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_hard_coded_project_relation_when_compiling_then_it_fails(
    test_case: PythonSqlReferenceErrorTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, {"sqlbuild_project.toml": _PROJECT_FILE} | test_case.files)

    with pytest.raises(ValueError) as error:
        compile_and_assemble(project_dir=tmp_path)

    rendered: str = (
        f"[{getattr(error.value, 'code', '')}] {error.value} {getattr(error.value, 'help', '')}"
    )
    assert all(fragment in rendered for fragment in test_case.expected_error_fragments)


@pytest.mark.parametrize(
    "test_case",
    (
        PythonSqlReferenceAllowedTestCase(
            description="non-project relations and a temporary table created by the hook",
            files={
                **_MODELS,
                _HOOK_PATH: python_hook_source(
                    body=(
                        '    ctx.execute_sql("CREATE TEMP TABLE customers AS SELECT 1 AS id")\n'
                        '    ctx.query("SELECT * FROM customers")\n'
                        '    ctx.query("SELECT * FROM information_schema.tables")\n'
                    )
                ),
            },
            expected_model_names=("customers", "orders"),
        ),
        PythonSqlReferenceAllowedTestCase(
            description="relation formatted from ctx.relation and a CTE named like a model",
            files={
                **_MODELS,
                _HOOK_PATH: python_hook_source(),
                _TASK_PATH: python_task_source(
                    body=(
                        '    orders = ctx.relation(model("orders"))\n'
                        '    ctx.query(f"SELECT * FROM {orders}")\n'
                        '    ctx.query("WITH customers AS (SELECT 1 AS id) SELECT * FROM customers")\n'
                    )
                ),
            },
            expected_model_names=("customers", "orders"),
        ),
        PythonSqlReferenceAllowedTestCase(
            description="hook naming the model it runs on",
            files={
                **_MODELS,
                _HOOK_PATH: python_hook_source(body='    ctx.query("SELECT * FROM orders")\n'),
            },
            expected_model_names=("customers", "orders"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_explicit_or_non_project_relations_when_compiling_then_it_succeeds(
    test_case: PythonSqlReferenceAllowedTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, {"sqlbuild_project.toml": _PROJECT_FILE} | test_case.files)

    project: CompiledProject = compile_and_assemble(project_dir=tmp_path)

    assert tuple(sorted(model.name for model in project.models)) == test_case.expected_model_names


@pytest.mark.parametrize(
    "test_case",
    (
        PythonSqlReferenceAllowedTestCase(
            description="enforcement disabled allows hard-coded names",
            files={
                **_MODELS,
                _HOOK_PATH: python_hook_source(),
                _TASK_PATH: python_task_source(
                    body='    ctx.query("SELECT count(*) FROM customers")\n'
                ),
            },
            expected_model_names=("customers", "orders"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_enforcement_disabled_when_compiling_hard_coded_names_then_it_succeeds(
    test_case: PythonSqlReferenceAllowedTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, {"sqlbuild_project.toml": _DISABLED_PROJECT_FILE} | test_case.files)

    project: CompiledProject = compile_and_assemble(project_dir=tmp_path)

    assert tuple(sorted(model.name for model in project.models)) == test_case.expected_model_names


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
