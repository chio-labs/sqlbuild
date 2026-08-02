"""CLI query command entry point."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import QueryResult
from sqlbuild.cli.commands._helpers.query.output import render_query_result
from sqlbuild.cli.commands._helpers.runtime.adapters import resolve_adapter
from sqlbuild.cli.commands._helpers.runtime.connection import (
    resolve_project_connection_config,
)
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)


def run_query(
    *,
    project_dir: Path | None,
    sql: str | None,
    query_file: Path | None = None,
    selected_target: str | None = None,
    output_format: str = "long",
    limit: int | None = 20,
) -> int:
    """Execute ad hoc SQL against the active project connection."""

    query_sql: str = _resolve_query_sql(sql=sql, query_file=query_file)
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


def _resolve_query_sql(*, sql: str | None, query_file: Path | None) -> str:
    if sql is not None and query_file is not None:
        raise CliUserError(
            "query accepts either positional SQL or --file, not both",
            code="C104",
        )
    if query_file is not None:
        query_sql: str = _read_query_file(query_file=query_file)
        if not query_sql.strip():
            raise CliUserError("query SQL must not be empty", code="C103")
        return query_sql
    if sql is None:
        raise CliUserError(
            "query requires SQL",
            code="C102",
            help="pass SQL as the query argument or use --file PATH",
        )
    query_sql = sql
    if not query_sql.strip():
        raise CliUserError("query SQL must not be empty", code="C103")
    return query_sql


def _read_query_file(*, query_file: Path) -> str:
    if not query_file.exists():
        raise CliUserError(f"query file does not exist: {query_file}", code="C105")
    if not query_file.is_file():
        raise CliUserError(f"query file path is not a file: {query_file}", code="C106")
    try:
        return query_file.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise CliUserError(
            f"query file could not be read as UTF-8: {query_file}",
            code="C107",
        ) from error
