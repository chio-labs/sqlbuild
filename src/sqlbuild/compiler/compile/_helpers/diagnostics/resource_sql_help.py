"""Concrete remediation for compile checks on SQL tests and audits."""

from __future__ import annotations

import re

from sqlbuild.compiler.compile._helpers.diagnostics.details import closest_column, missing_column
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.sql_analysis.models import SqlBindingDiagnostic

_SET_OPERATION_CODE: str = "B215"
_COMPARISON_CODE: str = "B217"
_UNKNOWN_COLUMN_CODE: str = "B002"
_SNOWFLAKE: str = "snowflake"
_SET_OPERATION_TYPES: re.Pattern[str] = re.compile(
    r"column (?P<position>\d+).*accumulated type (?P<left>[\w()]+), next type (?P<right>[\w()]+)",
    re.IGNORECASE,
)
_COMPARISON_TYPES: re.Pattern[str] = re.compile(
    r"between (?P<left>[\w()]+) and (?P<right>[\w()]+)", re.IGNORECASE
)
_ALIAS_NAME: re.Pattern[str] = re.compile(
    r"\s+AS\s+\"?(?P<name>[A-Za-z_][\w$]*)\"?,?$", re.IGNORECASE
)
_ALIAS_SUFFIX: re.Pattern[str] = re.compile(r"\s+AS\s+\"?[A-Za-z_][\w$]*\"?,?$", re.IGNORECASE)
_CAST: re.Pattern[str] = re.compile(r"CAST\((?P<inner>.+)\s+AS\s+[\w(), ]+\)", re.IGNORECASE)
_RELATION_PARAMETER: str = "@relation"
_LISTED_COLUMNS: int = 10
_SINGLE_OPERAND: re.Pattern[str] = re.compile(
    r"'(?:[^']|'')*'|[A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)?"
)
_WORD_CHARACTER: re.Pattern[str] = re.compile(r"[\w$]")
_PARAMETER: re.Pattern[str] = re.compile(r"@[A-Za-z_]\w*")
_TEXT_TYPES: tuple[str, ...] = ("VARCHAR", "STRING", "TEXT", "CHAR")
_TEMPORAL_TYPES: tuple[str, ...] = ("TIMESTAMP", "DATE")
_SET_OPERATION_KEYWORDS: frozenset[str] = frozenset(
    {"UNION", "ALL", "EXCEPT", "INTERSECT", "MINUS", "SELECT", "FROM", "DISTINCT", "BY", "NAME"}
)


def resource_sql_help(
    *,
    resource_type: CompiledResourceType,
    diagnostic: SqlBindingDiagnostic,
    authored_text: str,
    authored_line: str,
    column: int,
    authored_body: str,
    audit_definition: str | None,
    shapes: dict[str, dict[str, str]],
    relations: frozenset[str],
    dialect: str | None,
) -> str | None:
    """Return a concrete fix quoting the authored span, or None to keep the generic help."""

    if diagnostic.code == _SET_OPERATION_CODE:
        return _set_operation_help(
            message=diagnostic.message,
            authored_text=authored_text,
            authored_line=authored_line,
            span_column=column,
            sql_test=resource_type == CompiledResourceType.SQL_TEST,
            relation_shapes={name: shapes.get(name) or {} for name in relations},
        )
    if diagnostic.code == _COMPARISON_CODE and resource_type == CompiledResourceType.AUDIT:
        return _audit_comparison_help(
            message=diagnostic.message,
            authored_line=authored_line,
            column=column,
            authored_body=authored_body,
            audit_definition=audit_definition,
            dialect=dialect,
        )
    if diagnostic.code == _UNKNOWN_COLUMN_CODE and resource_type == CompiledResourceType.SQL_TEST:
        return _unknown_column_help(message=diagnostic.message, shapes=shapes)
    return None


def _set_operation_help(
    *,
    message: str,
    authored_text: str,
    authored_line: str,
    span_column: int,
    sql_test: bool,
    relation_shapes: dict[str, dict[str, str]],
) -> str | None:
    match: re.Match[str] | None = _SET_OPERATION_TYPES.search(message)
    if match is None:
        return None
    position: str = match.group("position")
    left: str = match.group("left").upper()
    right: str = match.group("right").upper()
    column: str = _set_operation_operand(
        authored_text=authored_text,
        authored_line=authored_line,
        column=span_column,
        position=position,
    )
    if not sql_test:
        return (
            "Cast one branch so both branches have the same type, for example "
            f"`CAST({column} AS {left})` for set-operation column {position}"
        )
    model_type: str | None = _model_type(
        authored_text=authored_text, operand=column, relation_shapes=relation_shapes
    )
    if model_type is not None:
        return (
            f"Cast set-operation column {position} to the tested model's type {model_type} in "
            f"the expected or fixture rows, for example `CAST({column} AS {model_type})`"
        )
    target: str = right if _is_text(left) and not _is_text(right) else left
    return (
        f"Cast set-operation column {position} explicitly so every branch has the same type, "
        f"for example `CAST({column} AS {target})` in the expected or fixture rows"
    )


def _model_type(
    *, authored_text: str, operand: str, relation_shapes: dict[str, dict[str, str]]
) -> str | None:
    """The tested relation's type for the branch column, when exactly one type matches."""

    names: list[str] = []
    alias: re.Match[str] | None = _ALIAS_NAME.search(authored_text.strip())
    if alias is not None:
        names.append(alias.group("name"))
    names.append(operand.rsplit(".", 1)[-1].strip('"'))
    for name in names:
        found: set[str] = set()
        for shape in relation_shapes.values():
            for output, value in shape.items():
                if output.casefold() == name.casefold() and value:
                    found.add(value.split("(", 1)[0].upper())
        if len(found) == 1:
            return found.pop()
    return None


def _audit_comparison_help(
    *,
    message: str,
    authored_line: str,
    column: int,
    authored_body: str,
    audit_definition: str | None,
    dialect: str | None,
) -> str | None:
    match: re.Match[str] | None = _COMPARISON_TYPES.search(message)
    if match is None:
        return None
    types: tuple[str, str] = (match.group("left").upper(), match.group("right").upper())
    temporal: str | None = _temporal_type(types)
    if temporal is None or not any(_is_text(value) for value in types):
        return None
    operand: str = _audit_parameter(
        authored_line=authored_line, column=column, authored_body=authored_body
    )
    conversion: str = (
        f"TO_{temporal}({operand})" if dialect == _SNOWFLAKE else f"CAST({operand} AS {temporal})"
    )
    audit: str = f"audit '{audit_definition}'" if audit_definition else "the audit"
    return (
        f"Convert the text value explicitly, for example `{conversion}`, "
        f"or attach {audit} to a {temporal} column"
    )


def _set_operation_operand(
    *, authored_text: str, authored_line: str, column: int, position: str
) -> str:
    """The authored branch operand when the span is exactly one, else the VALUES column name."""

    preceding: str = authored_line[column - 2 : column - 1] if column > 1 else ""
    expression: str = _ALIAS_SUFFIX.sub("", authored_text.strip().rstrip(","))
    cast: re.Match[str] | None = _CAST.fullmatch(expression)
    if cast is not None:
        expression = cast.group("inner").strip()
    if (
        not _WORD_CHARACTER.fullmatch(preceding)
        and _SINGLE_OPERAND.fullmatch(expression)
        and expression.upper() not in _SET_OPERATION_KEYWORDS
    ):
        return expression
    return f"COLUMN{position}"


def _audit_parameter(*, authored_line: str, column: int, authored_body: str) -> str:
    """The audit parameter nearest the finding on its line, else the body's only parameter."""

    on_line: list[re.Match[str]] = [
        match
        for match in _PARAMETER.finditer(authored_line)
        if match.group() != _RELATION_PARAMETER
    ]
    if on_line:
        return min(on_line, key=lambda match: abs(match.start() + 1 - column)).group()
    parameters: set[str] = set(_PARAMETER.findall(authored_body)) - {_RELATION_PARAMETER}
    return next(iter(parameters)) if len(parameters) == 1 else "<text expression>"


def _unknown_column_help(*, message: str, shapes: dict[str, dict[str, str]]) -> str | None:
    missing: tuple[str, str | None] | None = missing_column(message)
    if missing is None:
        return None
    name: str = missing[0]
    table: str | None = missing[1]
    if table is None:
        return None
    columns: dict[str, str] = shapes.get(table, {})
    suggestion: str | None = closest_column(name=name, columns=columns)
    if suggestion is not None:
        return f"did you mean '{suggestion}'?"
    listed: str = ", ".join(list(columns)[:_LISTED_COLUMNS])
    more: str = (
        f", and {len(columns) - _LISTED_COLUMNS} more" if len(columns) > _LISTED_COLUMNS else ""
    )
    outputs: str = f" (it outputs {listed}{more})" if columns else ""
    return f"'{table}' does not output '{name}'{outputs}; update the test to its current columns"


def _temporal_type(types: tuple[str, str]) -> str | None:
    for value in types:
        for kind in _TEMPORAL_TYPES:
            if value.startswith(kind):
                return kind
    return None


def _is_text(value: str) -> bool:
    return value.startswith(_TEXT_TYPES)
