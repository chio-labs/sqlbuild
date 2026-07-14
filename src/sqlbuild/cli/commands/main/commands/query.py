"""CLI query command entry point."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.models import QueryResult
from sqlbuild.cli.commands._helpers.query.output import render_query_result
from sqlbuild.cli.commands._helpers.runtime.adapters import resolve_adapter
from sqlbuild.cli.commands._helpers.runtime.connection import (
    resolve_project_connection_config,
)
from sqlbuild.cli.exceptions import CliUserError
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.resolution.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)


def run_query(
    *,
    project_dir: Path | None,
    sql: str | None,
    selected_target: str | None = None,
    output_format: str = "long",
    limit: int | None = 20,
) -> int:
    """Execute ad hoc SQL against the active project connection."""

    query_sql: str = _resolve_query_sql(sql=sql)
    if limit is not None and limit < 0:
        raise CliUserError(
            "query --limit must be greater than or equal to 0",
            code="C101",
            help="pass a non-negative integer or use --no-limit",
        )

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    adapter: BaseAdapter = resolve_adapter(
        adapter_name=resolve_effective_adapter_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        ),
        project_dir=effective_project_dir,
    )
    connection_config: dict[str, object] = resolve_project_connection_config(
        discovered_inputs=discovered_inputs,
        project_dir=effective_project_dir,
        selected_target=selected_target,
    )
    connection: object = adapter.connect(connection_config)
    try:
        result: QueryResult = adapter.query(connection=connection, sql=query_sql, limit=limit)
    finally:
        adapter.close(connection)

    sys.stdout.write(render_query_result(result=result, output_format=output_format, limit=limit))
    sys.stdout.flush()
    return 0


def _resolve_query_sql(*, sql: str | None) -> str:
    if sql is None:
        raise CliUserError("query requires SQL", code="C102", help="pass SQL as the query argument")
    query_sql: str = sql
    if not query_sql.strip():
        raise CliUserError("query SQL must not be empty", code="C103")
    return query_sql
