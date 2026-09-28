"""Python hooks that declare reads order their model after them and cannot read its dependants."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from sqlbuild.compiler.compile.models import CompiledProject
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    HookReadEdgeTestCase,
    HookReadErrorTestCase,
)
from tests.unit.src.sqlbuild.compiler.compile._helpers.helpers import (
    compile_and_assemble,
    execution_edge_names,
    gate_model,
    python_hook_source,
    render_compile_diagnostics,
)

_PROJECT_FILE: str = """
name = "demo"
adapter = "duckdb"

[settings]
sql_analysis = false
sql_validation = false
"""
_HOOK_PATH: str = "models/marts/_sqlbuild/_hooks/python/lookups.py"
_HOOKED_HEADER: str = 'MODEL (post_hooks [python("refresh_lookup")]);'
_COUNTRY_SEED: str = (
    "seeds:\n  - name: country_codes\n    columns:\n      - name: code\n        type: VARCHAR\n"
)
_SOURCES: str = "sources:\n  - name: raw_orders\n    table: orders\n"


@pytest.mark.parametrize(
    "test_case",
    (
        HookReadEdgeTestCase(
            description="hook reading a model makes the hooked model wait for it",
            files={
                _HOOK_PATH: python_hook_source(reads='model("customers")'),
                "models/marts/customers.sql": gate_model(sql="SELECT 1 AS customer_id"),
                "models/marts/orders.sql": gate_model(
                    sql="SELECT 1 AS order_id", header=_HOOKED_HEADER
                ),
            },
            expected_edges=(("orders", "customers"),),
        ),
        HookReadEdgeTestCase(
            description="hook reading a list of a seed and a source adds one edge per read",
            files={
                _HOOK_PATH: python_hook_source(
                    reads='[seed("country_codes"), source("raw_orders")]'
                ),
                "seeds/country_codes.yml": _COUNTRY_SEED,
                "seeds/country_codes.csv": "code\nGB\n",
                "sources/raw.yml": _SOURCES,
                "models/marts/orders.sql": gate_model(
                    sql="SELECT 1 AS order_id", header=_HOOKED_HEADER
                ),
            },
            expected_edges=(("orders", "country_codes"), ("orders", "raw_orders")),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_hook_reads_when_compiling_then_hooked_model_runs_after_reads(
    test_case: HookReadEdgeTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, {"sqlbuild_project.toml": _PROJECT_FILE} | test_case.files)

    project: CompiledProject = compile_and_assemble(project_dir=tmp_path)

    assert set(test_case.expected_edges) <= execution_edge_names(project=project)


@pytest.mark.parametrize(
    "test_case",
    (
        HookReadErrorTestCase(
            description="hook reading a model built from its own model",
            files={
                _HOOK_PATH: python_hook_source(reads='model("order_rollup")'),
                "models/marts/orders.sql": gate_model(
                    sql="SELECT 1 AS order_id", header=_HOOKED_HEADER
                ),
                "models/marts/order_rollup.sql": gate_model(
                    sql='SELECT count(*) AS n FROM __ref("orders")'
                ),
            },
            expected_error_fragments=(
                "[P007]",
                "Python hook 'refresh_lookup' on model 'orders' reads model 'order_rollup', "
                "which depends on 'orders'",
            ),
        ),
        HookReadErrorTestCase(
            description="every hook read of its own dependant is reported",
            files={
                _HOOK_PATH: python_hook_source(
                    reads='[model("order_rollup"), model("order_count")]'
                ),
                "models/marts/orders.sql": gate_model(
                    sql="SELECT 1 AS order_id", header=_HOOKED_HEADER
                ),
                "models/marts/order_rollup.sql": gate_model(
                    sql='SELECT count(*) AS n FROM __ref("orders")'
                ),
                "models/marts/order_count.sql": gate_model(
                    sql='SELECT count(*) AS n FROM __ref("orders")'
                ),
            },
            expected_error_fragments=(
                "[P007] Python hook 'refresh_lookup' on model 'orders' reads model 'order_count'",
                "[P007] Python hook 'refresh_lookup' on model 'orders' reads model 'order_rollup'",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_hook_reading_its_own_dependant_when_compiling_then_it_reports_p007(
    test_case: HookReadErrorTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, {"sqlbuild_project.toml": _PROJECT_FILE} | test_case.files)

    rendered: str = render_compile_diagnostics(project=compile_and_assemble(project_dir=tmp_path))

    assert all(fragment in rendered for fragment in test_case.expected_error_fragments)


@pytest.mark.parametrize(
    "test_case",
    (
        HookReadErrorTestCase(
            description="hook reading an unknown model",
            files={
                _HOOK_PATH: python_hook_source(reads='model("missing_customers")'),
                "models/marts/orders.sql": gate_model(
                    sql="SELECT 1 AS order_id", header=_HOOKED_HEADER
                ),
            },
            expected_error_fragments=(
                "Python hook 'refresh_lookup'",
                "reads unknown model 'missing_customers'",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_unsatisfiable_hook_reads_when_compiling_then_it_fails(
    test_case: HookReadErrorTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, {"sqlbuild_project.toml": _PROJECT_FILE} | test_case.files)

    with pytest.raises(ValueError) as error:
        compile_and_assemble(project_dir=tmp_path)

    rendered: str = f"[{getattr(error.value, 'code', '')}] {error.value}"
    assert all(fragment in rendered for fragment in test_case.expected_error_fragments)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
