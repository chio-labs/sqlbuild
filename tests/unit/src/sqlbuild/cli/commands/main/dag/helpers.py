from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.adapter.shared.models import QueryResult
from sqlbuild.integrations.duckdb.client import DuckDbAdapter


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
                'default_environment = "dev"',
                "",
                "[environments.dev]",
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
