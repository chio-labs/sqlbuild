"""CLI query command entry point."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import QueryResult
from sqlbuild.cli.commands.main.helpers.query.output import render_query_result
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import resolve_project_connection_config
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.models.project import resolve_effective_adapter_name


def run_query(
    project_dir: Path | None,
    sql: str | None,
    file_path: str | None = None,
    output_format: str = "long",
    limit: int | None = 20,
) -> int:
    """Execute ad hoc SQL against the active project connection."""

    query_sql: str = _resolve_query_sql(sql=sql, file_path=file_path)
    if limit is not None and limit < 0:
        raise CliUserError("query --limit must be greater than or equal to 0")

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    adapter: BaseAdapter = resolve_adapter(
        resolve_effective_adapter_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        )
    )
    connection_config: dict[str, object] = resolve_project_connection_config(
        discovered_inputs=discovered_inputs,
        project_dir=effective_project_dir,
    )
    connection: object = adapter.connect(connection_config)
    try:
        result: QueryResult = adapter.query(connection, query_sql, limit=limit)
    finally:
        adapter.close(connection)

    sys.stdout.write(render_query_result(result, output_format=output_format, limit=limit))
    sys.stdout.flush()
    return 0


def _resolve_query_sql(*, sql: str | None, file_path: str | None) -> str:
    if sql is not None and file_path is not None:
        raise CliUserError("query accepts either SQL or --file, not both")
    if file_path is not None:
        query_sql: str = Path(file_path).read_text(encoding="utf-8")
    elif sql is not None:
        query_sql = sql
    else:
        raise CliUserError("query requires SQL or --file")
    if not query_sql.strip():
        raise CliUserError("query SQL must not be empty")
    return query_sql
