"""Native Polyglot schema-validation implementation."""

from __future__ import annotations

import json
import re
from typing import Any, cast

import sqlbuild._native as _native
from sqlbuild.compiler.sql_analysis.constants import NATIVE_DIALECT_ALIASES, TYPE_CHECKED_DIALECTS
from sqlbuild.compiler.sql_analysis.exceptions import SqlAnalysisBoundaryError
from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql
from sqlbuild.compiler.sql_analysis.models import (
    SqlBindingDiagnostic,
    SqlBindingResult,
    SqlSchemaValidationRequest,
)
from sqlbuild.compiler.sql_analysis.types import NativeValidationModule

_SQLBUILD_CODE_BY_NATIVE_CODE: dict[str, str] = {
    "E200": "B000",
    "E201": "B002",
    "E221": "B003",
    "E222": "B004",
    "E223": "B005",
    "E202": "B101",
    "E203": "B102",
    "E210": "B210",
    "E211": "B211",
    "E212": "B212",
    "E213": "B213",
    "E214": "B214",
    "E215": "B215",
    "E216": "B216",
    "E217": "B217",
    "E218": "B218",
    "E219": "B219",
    "E230": "B230",
    "E231": "B231",
    "E232": "B232",
}
_ERROR_SEVERITY: str = "error"
_NATIVE_UNKNOWN_COLUMN_CODE: str = "E201"
_NATIVE_AMBIGUOUS_COLUMN_CODE: str = "E221"
_ORDER_BY_CONTEXT: str = "ORDER BY"
_WINDOW_ORDER_BY_CONTEXT: str = "WINDOW ORDER BY"
_SNOWFLAKE_DIALECT: str = "snowflake"
_SELECT_KIND: str = "select"
_IMPLICIT_VALUES_COLUMN_PATTERN: re.Pattern[str] = re.compile(
    r"^Unknown column '(column([1-9][0-9]*))'$",
    flags=re.IGNORECASE,
)
_UNKNOWN_COLUMN_PATTERN: re.Pattern[str] = re.compile(
    r"^Unknown column '([^']+)'(?: in table '[^']+'| \(not found in any referenced table\))$"
)
_AMBIGUOUS_UNQUALIFIED_COLUMN_PATTERN: re.Pattern[str] = re.compile(
    r"^Ambiguous unqualified column '([^']+)' found in [0-9]+ referenced tables$"
)


def get_schema_validations(
    *, requests: tuple[SqlSchemaValidationRequest, ...]
) -> tuple[SqlBindingResult, ...]:
    """Validate a SQL batch without exposing Polyglot payloads."""

    payloads: list[dict[str, object]] = [_request_payload(request=request) for request in requests]
    responses: Any = json.loads(
        cast(NativeValidationModule, _native).validate_sql_with_schemas_json(
            json.dumps(payloads, separators=(",", ":"), sort_keys=True)
        )
    )
    if not isinstance(responses, list) or len(responses) != len(requests):
        raise SqlAnalysisBoundaryError(
            "native SQL schema validation returned an invalid batch response"
        )
    return tuple(
        _binding_result(sql=request.sql, dialect=request.dialect, response=response)
        for request, response in zip(requests, responses, strict=True)
    )


def _request_payload(*, request: SqlSchemaValidationRequest) -> dict[str, object]:
    dialect: str = NATIVE_DIALECT_ALIASES.get(
        request.dialect or "generic", request.dialect or "generic"
    )
    tables: list[dict[str, object]] = []
    for table_name, columns in sorted(request.schema.items()):
        table_columns: list[dict[str, str]] = []
        for column_name, column_type in columns.items():
            table_columns.append({"name": column_name, "type": column_type or "UNKNOWN"})
        tables.append({"name": table_name, "columns": table_columns})
    return {
        "sql": request.sql,
        "dialect": dialect,
        "schema": {
            "strict": True,
            "tables": tables,
        },
        "options": {
            "check_types": dialect.lower() in TYPE_CHECKED_DIALECTS,
            "check_references": True,
            "strict": True,
            "semantic": True,
            "strict_syntax": False,
        },
    }


def _binding_result(*, sql: str, dialect: str | None, response: object) -> SqlBindingResult:
    response_dict: dict[str, object] | None = (
        cast(dict[str, object], response) if isinstance(response, dict) else None
    )
    errors: object = response_dict.get("errors") if response_dict is not None else None
    if not isinstance(errors, list):
        raise SqlAnalysisBoundaryError("native SQL schema validation returned an invalid response")
    diagnostics: list[SqlBindingDiagnostic] = []
    for value in errors:
        if not isinstance(value, dict):
            continue
        value_dict: dict[str, object] = cast(dict[str, object], value)
        if value_dict.get("severity") != _ERROR_SEVERITY:
            continue
        native_code: object = value_dict.get("code")
        if not isinstance(native_code, str) or native_code not in _SQLBUILD_CODE_BY_NATIVE_CODE:
            continue
        raw_message: str = str(value_dict.get("message") or "SQL binding failed")
        context: str | None = _diagnostic_context(sql=sql, message=raw_message)
        message: str = f"{raw_message} (context: {context})" if context is not None else raw_message
        line: int | None
        column: int | None
        line, column = _diagnostic_position(
            sql=sql,
            message=message,
            line=_optional_int(value_dict.get("line")),
            column=_optional_int(value_dict.get("column")),
        )
        start: int | None = _optional_int(value_dict.get("start"))
        if start is not None and 0 <= start < len(sql):
            line = sql.count("\n", 0, start) + 1
            column = start - sql.rfind("\n", 0, start)
        if _is_proven_snowflake_values_column(
            sql=sql,
            dialect=dialect,
            message=raw_message,
            line=line,
            column=column,
        ) or _is_proven_snowflake_output_alias(
            sql=sql,
            dialect=dialect,
            native_code=native_code,
            message=raw_message,
        ):
            continue
        diagnostics.append(
            SqlBindingDiagnostic(
                code=_SQLBUILD_CODE_BY_NATIVE_CODE[native_code],
                message=message,
                line=line,
                column=column,
                start=_optional_int(value_dict.get("start")),
                end=_optional_int(value_dict.get("end")),
            )
        )
    return SqlBindingResult(diagnostics=tuple(diagnostics))


def _is_proven_snowflake_values_column(
    *,
    sql: str,
    dialect: str | None,
    message: str,
    line: int | None,
    column: int | None,
) -> bool:
    if (dialect or "").lower() != _SNOWFLAKE_DIALECT or line is None or column is None:
        return False
    match: re.Match[str] | None = _IMPLICIT_VALUES_COLUMN_PATTERN.fullmatch(message)
    if match is None:
        return False
    column_name: str = match.group(1)
    ordinal: int = int(match.group(2))
    polyglot_module: Any = import_polyglot_sql()
    try:
        parsed: Any = polyglot_module.parse_one(sql, dialect=_SNOWFLAKE_DIALECT)
    except polyglot_module.PolyglotError:
        return False
    selects: list[Any] = []
    if str(getattr(parsed, "kind", "")) == _SELECT_KIND:
        selects.append(parsed)
    selects.extend(parsed.find_all(_SELECT_KIND))
    return any(
        _select_proves_implicit_values_column(
            select=select,
            sql=sql,
            column_name=column_name,
            ordinal=ordinal,
            line=line,
            column=column,
        )
        for select in selects
    )


def _select_proves_implicit_values_column(
    *,
    select: Any,
    sql: str,
    column_name: str,
    ordinal: int,
    line: int,
    column: int,
) -> bool:
    payload: object = select.to_dict().get(_SELECT_KIND)
    if not isinstance(payload, dict):
        return False
    select_payload: dict[str, object] = cast(dict[str, object], payload)
    if select_payload.get("joins"):
        return False
    from_payload: object = select_payload.get("from")
    if not isinstance(from_payload, dict):
        return False
    relations: object = cast(dict[str, object], from_payload).get("expressions")
    if not isinstance(relations, list) or len(relations) != 1:
        return False
    relation: object = relations[0]
    if not isinstance(relation, dict):
        return False
    values: object = cast(dict[str, object], relation).get("values")
    if not isinstance(values, dict):
        return False
    values_payload: dict[str, object] = cast(dict[str, object], values)
    if values_payload.get("alias") is not None or values_payload.get("column_aliases"):
        return False
    rows: object = values_payload.get("expressions")
    if not isinstance(rows, list) or not rows:
        return False
    row_widths: list[int] = []
    for row in rows:
        if not isinstance(row, dict):
            return False
        expressions: object = cast(dict[str, object], row).get("expressions")
        if not isinstance(expressions, list):
            return False
        row_widths.append(len(expressions))
    if any(width < ordinal for width in row_widths):
        return False
    projections: object = select_payload.get("expressions")
    if not isinstance(projections, list):
        return False
    return any(
        _projection_is_implicit_values_column(
            projection=projection,
            sql=sql,
            column_name=column_name,
            line=line,
            column=column,
        )
        for projection in projections
    )


def _projection_is_implicit_values_column(
    *, projection: object, sql: str, column_name: str, line: int, column: int
) -> bool:
    if not isinstance(projection, dict):
        return False
    expression: object = projection
    alias_payload: object = cast(dict[str, object], projection).get("alias")
    if isinstance(alias_payload, dict):
        expression = cast(dict[str, object], alias_payload).get("this")
    if not isinstance(expression, dict):
        return False
    column_payload: object = cast(dict[str, object], expression).get("column")
    if not isinstance(column_payload, dict):
        return False
    column_dict: dict[str, object] = cast(dict[str, object], column_payload)
    if column_dict.get("table") is not None:
        return False
    name_payload: object = column_dict.get("name")
    if not isinstance(name_payload, dict):
        return False
    name_dict: dict[str, object] = cast(dict[str, object], name_payload)
    if (
        name_dict.get("quoted") is True
        or str(name_dict.get("name") or "").lower() != column_name.lower()
    ):
        return False
    span: object = column_dict.get("span")
    if not isinstance(span, dict):
        return False
    start: object = cast(dict[str, object], span).get("start")
    if not isinstance(start, int):
        return False
    candidate_line: int = sql.count("\n", 0, start) + 1
    candidate_column: int = start - sql.rfind("\n", 0, start)
    return (candidate_line, candidate_column) == (line, column)


def _is_proven_snowflake_output_alias(
    *, sql: str, dialect: str | None, native_code: str, message: str
) -> bool:
    if (dialect or "").lower() != _SNOWFLAKE_DIALECT:
        return False
    column_name: str | None = _output_alias_diagnostic_column(
        native_code=native_code,
        message=message,
    )
    if column_name is None:
        return False
    polyglot_module: Any = import_polyglot_sql()
    try:
        parsed: Any = polyglot_module.parse_one(sql, dialect=_SNOWFLAKE_DIALECT)
    except polyglot_module.PolyglotError:
        return False
    selects: list[Any] = []
    if str(getattr(parsed, "kind", "")) == _SELECT_KIND:
        selects.append(parsed)
    selects.extend(parsed.find_all(_SELECT_KIND))
    return any(
        _select_proves_output_alias(
            select=select,
            column_name=column_name,
            native_code=native_code,
        )
        for select in selects
    )


def _output_alias_diagnostic_column(*, native_code: str, message: str) -> str | None:
    pattern: re.Pattern[str]
    if native_code == _NATIVE_UNKNOWN_COLUMN_CODE:
        pattern = _UNKNOWN_COLUMN_PATTERN
    elif native_code == _NATIVE_AMBIGUOUS_COLUMN_CODE:
        pattern = _AMBIGUOUS_UNQUALIFIED_COLUMN_PATTERN
    else:
        return None
    match: re.Match[str] | None = pattern.fullmatch(message)
    return match.group(1) if match is not None else None


def _select_proves_output_alias(*, select: Any, column_name: str, native_code: str) -> bool:
    payload: object = select.to_dict().get(_SELECT_KIND)
    if not isinstance(payload, dict):
        return False
    select_payload: dict[str, object] = cast(dict[str, object], payload)
    projections: object = select_payload.get("expressions")
    if not isinstance(projections, list):
        return False
    aliases: set[str] = set()
    for projection in projections:
        expression, alias = _projection_expression_and_alias(projection)
        if native_code == _NATIVE_UNKNOWN_COLUMN_CODE and column_name.lower() in aliases:
            if _payload_contains_unqualified_column(
                payload=expression,
                column_name=column_name,
            ):
                return True
        if alias is not None:
            aliases.add(alias.lower())
    if column_name.lower() not in aliases:
        return False
    if native_code == _NATIVE_UNKNOWN_COLUMN_CODE:
        return _payload_contains_unqualified_column(
            payload=select_payload.get("where_clause"),
            column_name=column_name,
        )
    return _payload_contains_unqualified_column(
        payload=select_payload.get("order_by"),
        column_name=column_name,
    )


def _projection_expression_and_alias(projection: object) -> tuple[object, str | None]:
    if not isinstance(projection, dict):
        return projection, None
    alias_payload: object = cast(dict[str, object], projection).get("alias")
    if not isinstance(alias_payload, dict):
        return projection, None
    alias_dict: dict[str, object] = cast(dict[str, object], alias_payload)
    name_payload: object = alias_dict.get("alias")
    if not isinstance(name_payload, dict):
        return alias_dict.get("this"), None
    name_dict: dict[str, object] = cast(dict[str, object], name_payload)
    alias: str | None = (
        str(name_dict.get("name"))
        if name_dict.get("quoted") is not True and name_dict.get("name") is not None
        else None
    )
    return alias_dict.get("this"), alias


def _payload_contains_unqualified_column(*, payload: object, column_name: str) -> bool:
    if isinstance(payload, list | tuple):
        return any(
            _payload_contains_unqualified_column(payload=value, column_name=column_name)
            for value in payload
        )
    if not isinstance(payload, dict):
        return False
    payload_dict: dict[str, object] = cast(dict[str, object], payload)
    column_payload: object = payload_dict.get("column")
    if isinstance(column_payload, dict):
        column_dict: dict[str, object] = cast(dict[str, object], column_payload)
        name_payload: object = column_dict.get("name")
        if isinstance(name_payload, dict):
            name_dict: dict[str, object] = cast(dict[str, object], name_payload)
            if (
                column_dict.get("table") is None
                and name_dict.get("quoted") is not True
                and str(name_dict.get("name") or "").lower() == column_name.lower()
            ):
                return True
    return any(
        key != _SELECT_KIND
        and _payload_contains_unqualified_column(payload=value, column_name=column_name)
        for key, value in payload_dict.items()
    )


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
