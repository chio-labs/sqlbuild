from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.adapter.contract.models import QueryResult
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter


class NoConnectDuckDbAdapter(DuckDbAdapter):
    """DuckDB adapter test double that fails if dag opens a connection."""

    def connect(self, config: dict[str, Any]) -> Any:
        del config
        raise AssertionError("dag should not connect")

    def execute(self, connection: Any, sql: str) -> Any:
        del connection, sql
        raise AssertionError("dag should not execute SQL")

    def query(self, connection: Any, sql: str, *, limit: int | None) -> QueryResult:
        del connection, sql, limit
        raise AssertionError("dag should not query")

    def close(self, connection: Any) -> None:
        del connection
        raise AssertionError("dag should not close a connection")


def prepare_static_dag_project(root: Path) -> Path:
    """Create a minimal local project for dag command tests."""

    project_dir: Path = root / "project"
    models_dir: Path = project_dir / "models"
    models_dir.mkdir(parents=True)
    (project_dir / "sqlbuild_project.toml").write_text(
        "\n".join(
            (
                'name = "dag_project"',
                'adapter = "duckdb"',
                'default_target = "dev"',
                "",
                "[targets.dev]",
                'schema = "analytics"',
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (models_dir / "orders.sql").write_text(
        "MODEL (materialized table);\n\nSELECT 1 AS order_id\n",
        encoding="utf-8",
    )
    return project_dir


def prepare_python_dag_project(root: Path) -> Path:
    """Create a local project with Python tasks, assets, and checks."""

    project_dir: Path = prepare_static_dag_project(root)
    tasks_dir: Path = project_dir / "tasks"
    assets_dir: Path = project_dir / "assets"
    loaders_dir: Path = project_dir / "loaders"
    checks_dir: Path = project_dir / "checks"
    tasks_dir.mkdir()
    assets_dir.mkdir()
    loaders_dir.mkdir()
    checks_dir.mkdir()
    (tasks_dir / "prepare_orders.py").write_text(
        "\n".join(
            (
                "from sqlbuild.tasks import task",
                "from sqlbuild.refs import model",
                "",
                "@task(",
                "    depends_on=model('orders'),",
                "    tags=['daily'],",
                "    group='python',",
                "    meta={'owner': 'data'},",
                ")",
                "def prepare_orders(ctx):",
                "    return ctx.result(payload={'rows': 1}, metadata={'source': 'fixture'})",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (loaders_dir / "warehouse_export.py").write_text(
        "\n".join(
            (
                "from sqlbuild.loaders import loader",
                "from tasks.prepare_orders import prepare_orders",
                "",
                "@loader(",
                "    depends_on=(prepare_orders,),",
                "    columns=[{'name': 'order_id', 'type': 'integer'}],",
                ")",
                "def warehouse_export(ctx):",
                "    return [{'order_id': 1}]",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (assets_dir / "orders_export.py").write_text(
        "\n".join(
            (
                "from sqlbuild.assets import asset",
                "from loaders.warehouse_export import warehouse_export",
                "from tasks.prepare_orders import prepare_orders",
                "",
                "@asset(",
                "    depends_on=(prepare_orders, warehouse_export),",
                "    tags=['daily', 'external'],",
                "    group='exports',",
                "    description='Orders export artifact',",
                "    meta={'system': 'object_store'},",
                "    columns=[{'name': 'order_id', 'type': 'integer'}],",
                "    column_lineage={",
                "        'order_id': [{'node': 'prepare_orders', 'column': 'order_id'}]",
                "    },",
                ")",
                "def orders_export(ctx):",
                "    return ctx.result(materialized=True)",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (checks_dir / "check_orders_export.py").write_text(
        "\n".join(
            (
                "from sqlbuild.checks import check",
                "from assets.orders_export import orders_export",
                "from loaders.warehouse_export import warehouse_export",
                "from tasks.prepare_orders import prepare_orders",
                "",
                "@check(",
                "    depends_on=(orders_export, prepare_orders, warehouse_export),",
                "    tags=['daily'],",
                "    group='exports',",
                "    description='Orders export is present',",
                "    meta={'owner': 'quality'},",
                ")",
                "def check_orders_export(ctx):",
                "    return True",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (checks_dir / "check_loader_export.py").write_text(
        "\n".join(
            (
                "from sqlbuild.checks import check",
                "from loaders.warehouse_export import warehouse_export",
                "",
                "@check(depends_on=warehouse_export, tags=['loader'])",
                "def check_loader_export(ctx):",
                "    return ctx.pass_(message='loader rows available')",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return project_dir
