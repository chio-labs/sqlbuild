from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent

from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import build_virtual_plan_project_toml
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import prepare_inline_project, run_sqb


def prepare_freshness_project(
    *,
    tmp_path: Path,
    raw_orders_freshness: str | None = None,
    include_error_source: bool = True,
    include_managed_source: bool = False,
) -> Path:
    repo_files: dict[str, str] = {
        "sqlbuild_project.toml": (
            'name = "freshness_command"\n'
            'adapter = "duckdb"\n\n'
            "[connection]\n"
            'database = "warehouse.duckdb"\n'
        ),
        "sources/raw.yml": freshness_sources_yml(
            raw_orders_freshness=raw_orders_freshness,
            include_error_source=include_error_source,
            include_managed_source=include_managed_source,
        ),
        "models/orders.sql": (
            'MODEL (materialized table);\n\nSELECT * FROM __source("raw_orders")\n'
        ),
    }
    if include_managed_source:
        repo_files["loaders/raw.py"] = (
            "from sqlbuild.loaders import loader\n\n"
            "@loader\n"
            "def raw_managed(ctx):\n"
            "    return [{'event_id': 5}]\n"
        )
    return prepare_inline_project(
        tmp_path=tmp_path,
        project_name="freshness_command",
        repo_files=repo_files,
    )


def prepare_multi_schema_freshness_project(*, tmp_path: Path) -> Path:
    return prepare_inline_project(
        tmp_path=tmp_path,
        project_name="multi_schema_freshness_command",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "multi_schema_freshness_command"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "sources/raw.yml": freshness_sources_yml(include_error_source=False),
            "models/dev_orders.sql": (
                'MODEL (materialized table, schema dev);\n\nSELECT * FROM __source("raw_orders")\n'
            ),
            "models/mart_orders.sql": (
                'MODEL (materialized table, schema mart);\n\nSELECT * FROM __source("raw_orders")\n'
            ),
        },
    )


def prepare_virtual_freshness_project(
    *, tmp_path: Path, raw_orders_freshness: str | None = None
) -> Path:
    freshness: str = raw_orders_freshness or (
        "                    freshness:\n"
        "                      strategy: column\n"
        "                      column: data_version\n"
        "                      type: integer\n"
    )
    return prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_freshness_command",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml(),
            "sources/raw.yml": dedent(
                f"""
                sources:
                  - name: raw_orders
                    schema: raw
                    table: raw_orders
{freshness.rstrip()}
                """
            ).strip()
            + "\n",
            "models/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __source("raw_orders")\n'
            ),
        },
    )


def persist_virtual_source_freshness(*, project_dir: Path) -> None:
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stdout + init_result.stderr
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr


def freshness_sources_yml(
    *,
    raw_orders_query: str = "SELECT 1 AS data_version",
    raw_orders_freshness: str | None = None,
    include_error_source: bool = True,
    include_managed_source: bool = False,
) -> str:
    freshness: str = raw_orders_freshness or (
        "    freshness:\n"
        "      strategy: sql\n"
        "      type: integer\n"
        f"      query: {raw_orders_query}\n"
    )
    error_source: str = (
        "  - name: raw_error\n"
        "    expression: SELECT 3 AS order_id\n"
        "    freshness:\n"
        "      strategy: sql\n"
        "      type: integer\n"
        "      query: SELECT missing_column AS data_version\n"
        if include_error_source
        else ""
    )
    managed_source: str = (
        "  - name: raw_managed\n"
        "    managed: true\n"
        "    expression: SELECT 5 AS event_id\n"
        "    freshness:\n"
        "      strategy: sql\n"
        "      type: integer\n"
        "      query: SELECT 5 AS data_version\n"
        if include_managed_source
        else ""
    )
    return (
        "sources:\n"
        "  - name: raw_orders\n"
        "    expression: SELECT 1 AS order_id\n"
        f"{freshness}"
        f"{error_source}"
        f"{managed_source}"
        "  - name: raw_unknown\n"
        "    expression: SELECT 2 AS order_id\n"
    )


def persist_standard_source_freshness(*, project_dir: Path) -> None:
    initial_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert initial_build_result.returncode == 0, (
        initial_build_result.stdout + initial_build_result.stderr
    )
    changes_only_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert changes_only_result.returncode == 0, (
        changes_only_result.stdout + changes_only_result.stderr
    )
