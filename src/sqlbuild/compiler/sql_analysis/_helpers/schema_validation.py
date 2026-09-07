"""Native Polyglot schema-validation implementation."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any, cast

import sqlbuild._native as _native
from sqlbuild.compiler.sql_analysis.exceptions import SqlAnalysisBoundaryError
from sqlbuild.compiler.sql_analysis.models import SqlBindingDiagnostic, SqlBindingResult
from sqlbuild.compiler.sql_analysis.types import NativeValidationModule

_SQLBUILD_CODE_BY_NATIVE_CODE: dict[str, str] = {
    "E200": "B000",
    "E201": "B002",
    "E221": "B003",
    "E222": "B004",
    "E223": "B005",
}
_ERROR_SEVERITY: str = "error"
_ORDER_BY_CONTEXT: str = "ORDER BY"
_WINDOW_ORDER_BY_CONTEXT: str = "WINDOW ORDER BY"


def get_schema_validation(
    *,
    sql: str,
    dialect: str | None,
    schema: Mapping[str, Mapping[str, str]],
) -> SqlBindingResult:
    """Validate SQL against complete relation schemas without exposing Polyglot payloads."""

    tables: list[dict[str, object]] = []
    for table_name, columns in sorted(schema.items()):
        table_columns: list[dict[str, str]] = []
        for column_name, column_type in columns.items():
            table_columns.append({"name": column_name, "type": column_type or "UNKNOWN"})
        tables.append({"name": table_name, "columns": table_columns})
    request: dict[str, object] = {
        "sql": sql,
        "dialect": dialect or "generic",
        "schema": {
            "strict": True,
            "tables": tables,
        },
        "options": {
            "check_types": False,
            "check_references": True,
            "strict": True,
            "semantic": False,
            "strict_syntax": False,
        },
    }
    response: Any = json.loads(
        cast(NativeValidationModule, _native).validate_sql_with_schema_json(
            json.dumps(request, separators=(",", ":"), sort_keys=True)
        )
    )
    errors: object = response.get("errors") if isinstance(response, dict) else None
    if not isinstance(errors, list):
        raise SqlAnalysisBoundaryError("native SQL schema validation returned an invalid response")
    diagnostics: list[SqlBindingDiagnostic] = []
    for value in errors:
        if not isinstance(value, dict) or value.get("severity") != _ERROR_SEVERITY:
            continue
        native_code: object = value.get("code")
        if not isinstance(native_code, str) or native_code not in _SQLBUILD_CODE_BY_NATIVE_CODE:
            continue
        raw_message: str = str(value.get("message") or "SQL binding failed")
        context: str | None = _diagnostic_context(sql=sql, message=raw_message)
        message: str = f"{raw_message} (context: {context})" if context is not None else raw_message
        line, column = _diagnostic_position(
            sql=sql,
            message=message,
            line=_optional_int(value.get("line")),
            column=_optional_int(value.get("column")),
        )
        diagnostics.append(
            SqlBindingDiagnostic(
                code=_SQLBUILD_CODE_BY_NATIVE_CODE[native_code],
                message=message,
                line=line,
                column=column,
                start=_optional_int(value.get("start")),
                end=_optional_int(value.get("end")),
            )
        )
    return SqlBindingResult(diagnostics=tuple(diagnostics))


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _diagnostic_position(
    *, sql: str, message: str, line: int | None, column: int | None
) -> tuple[int | None, int | None]:
    if line is not None and column is not None:
        return line, column
    match: re.Match[str] | None = re.search(
        r"(?:Unknown column|Ambiguous column reference) '([^']+)'", message
    )
    if match is None:
        return line, column
    identifier: str = match.group(1).rsplit(".", maxsplit=1)[-1]
    occurrences: list[re.Match[str]] = list(
        re.finditer(rf"(?<![A-Za-z0-9_]){re.escape(identifier)}(?![A-Za-z0-9_])", sql)
    )
    if len(occurrences) != 1:
        return line, column
    start: int = occurrences[0].start()
    return sql.count("\n", 0, start) + 1, start - sql.rfind("\n", 0, start)


def _diagnostic_context(*, sql: str, message: str) -> str | None:
    match: re.Match[str] | None = re.search(
        r"(?:Unknown column|Ambiguous column reference) '([^']+)'", message
    )
    if match is None:
        return None
    identifier: str = match.group(1).rsplit(".", maxsplit=1)[-1]
    occurrence: re.Match[str] | None = re.search(
        rf"(?<![A-Za-z0-9_]){re.escape(identifier)}(?![A-Za-z0-9_])", sql
    )
    if occurrence is None:
        return None
    prefix: str = sql[: occurrence.start()]
    candidates: tuple[tuple[str, str], ...] = (
        ("JOIN USING", r"\bUSING\s*\("),
        ("QUALIFY", r"\bQUALIFY\b"),
        ("HAVING", r"\bHAVING\b"),
        ("GROUP BY", r"\bGROUP\s+BY\b"),
        ("ORDER BY", r"\bORDER\s+BY\b"),
        ("WINDOW PARTITION BY", r"\bPARTITION\s+BY\b"),
        ("JOIN ON", r"\bON\b"),
        ("WHERE", r"\bWHERE\b"),
        ("SELECT", r"\bSELECT\b"),
    )
    latest: tuple[int, str] | None = None
    for label, pattern in candidates:
        matches: list[re.Match[str]] = list(re.finditer(pattern, prefix, flags=re.IGNORECASE))
        if matches and (latest is None or matches[-1].start() > latest[0]):
            latest = matches[-1].start(), label
    if latest is None:
        return None
    if latest[1] == _ORDER_BY_CONTEXT:
        over_position: int = prefix.upper().rfind("OVER")
        if over_position > latest[0] or (
            over_position >= 0
            and prefix[over_position:].count("(") > prefix[over_position:].count(")")
        ):
            return _WINDOW_ORDER_BY_CONTEXT
    return latest[1]
