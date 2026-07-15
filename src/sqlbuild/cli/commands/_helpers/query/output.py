"""Output formatters for ad hoc query results."""

from __future__ import annotations

import csv
import io
import json
from decimal import Decimal
from typing import Any

from sqlbuild.adapter.contract.models import QueryResult
from sqlbuild.cli.commands.exceptions import CliUserError

_LONG_OUTPUT_FORMAT: str = "long"
_TABLE_OUTPUT_FORMAT: str = "table"
_JSON_OUTPUT_FORMAT: str = "json"
_CSV_OUTPUT_FORMAT: str = "csv"


def render_query_result(*, result: QueryResult, output_format: str, limit: int | None) -> str:
    """Render a query result using the requested output format."""

    if not result.columns:
        return "OK\n"
    if output_format == _LONG_OUTPUT_FORMAT:
        return render_long_query_result(result=result, limit=limit)
    if output_format == _TABLE_OUTPUT_FORMAT:
        return render_table_query_result(result=result, limit=limit)
    if output_format == _JSON_OUTPUT_FORMAT:
        return render_json_query_result(result)
    if output_format == _CSV_OUTPUT_FORMAT:
        return render_csv_query_result(result)
    raise CliUserError(f"unsupported query output format '{output_format}'")


def render_long_query_result(*, result: QueryResult, limit: int | None) -> str:
    lines: list[str] = []
    column_width: int = max(len(column) for column in result.columns)
    row_index: int
    row: tuple[object, ...]
    for row_index, row in enumerate(result.rows, start=1):
        if lines:
            lines.append("")
        header: str = f"-[ RECORD {row_index} ]"
        lines.append(header + "-" * max(0, 40 - len(header)) + "+")
        column: str
        value: object
        for column, value in zip(result.columns, row, strict=True):
            lines.append(f"{column:<{column_width}} | {_format_display_value(value)}")
    lines.append("")
    lines.append(_format_row_count(len(result.rows)))
    if result.truncated:
        lines.append(_format_truncated_message(limit))
    return "\n".join(lines) + "\n"


def render_table_query_result(*, result: QueryResult, limit: int | None) -> str:
    display_rows: list[tuple[str, ...]] = []
    source_row: tuple[object, ...]
    for source_row in result.rows:
        display_values: list[str] = []
        source_value: object
        for source_value in source_row:
            display_values.append(_format_display_value(source_value))
        display_rows.append(tuple(display_values))
    rows: tuple[tuple[str, ...], ...] = tuple(display_rows)
    widths: list[int] = [len(column) for column in result.columns]
    row: tuple[str, ...]
    for row in rows:
        index: int
        value: str
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))
    separator: str = " | "
    lines: list[str] = [
        separator.join(column.ljust(widths[index]) for index, column in enumerate(result.columns)),
        separator.join("-" * width for width in widths),
    ]
    for row in rows:
        lines.append(
            separator.join(value.ljust(widths[index]) for index, value in enumerate(row)).rstrip()
        )
    lines.append("")
    lines.append(_format_row_count(len(result.rows)))
    if result.truncated:
        lines.append(_format_truncated_message(limit))
    return "\n".join(lines) + "\n"


def render_json_query_result(result: QueryResult) -> str:
    rows: list[dict[str, object]] = [
        dict(zip(result.columns, row, strict=True)) for row in result.rows
    ]
    return json.dumps(rows, default=_json_default) + "\n"


def render_csv_query_result(result: QueryResult) -> str:
    stream: io.StringIO = io.StringIO()
    writer: Any = csv.writer(stream, lineterminator="\n")
    writer.writerow(result.columns)
    writer.writerows(result.rows)
    return stream.getvalue()


def _format_display_value(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def _format_row_count(count: int) -> str:
    noun: str = "row" if count == 1 else "rows"
    return f"{count} {noun}"


def _format_truncated_message(limit: int | None) -> str:
    if limit is None:
        return ""
    return f"Showing {limit} rows. Use --limit to show more or --no-limit to disable the limit."


def _json_default(value: object) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)
