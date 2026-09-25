"""Explain semantic diagnostics using the query's actual input schemas."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from sqlbuild.compiler.compile._helpers.analysis.compact import get_complete_schema_binding_request
from sqlbuild.compiler.compile._helpers.assembly.semantic_shapes import semantic_shapes
from sqlbuild.compiler.compile._helpers.diagnostics.help import (
    comparison_help,
    semantic_help,
)
from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject, CompilerDiagnostic
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql
from sqlbuild.compiler.sql_analysis.models import SqlSchemaValidationRequest
from sqlbuild.spec.contracts.models import SourceLocation

_UNKNOWN_COLUMN: str = "B002"
_COMPARISON: str = "B217"
_MIN_ABBREVIATION_LENGTH: int = 3
_MAX_EDIT_DISTANCE: int = 2
_DISPLAY_LIMIT: int = 10
_QUALIFIER_SEPARATOR: str = "."
_COLUMN_KIND: str = "column"
_TYPE_CODES: frozenset[str] = frozenset(f"B21{i}" for i in range(10))
_TYPE_WORDS: str = (
    r"\b(timestamp|integer|varchar|boolean|date|interval|double|float|decimal|numeric|"
    r"bigint|smallint|text|time|string|binary|array|struct)\b"
)
_MISSING: re.Pattern[str] = re.compile(r"Unknown column '([^']+)'(?: in table '([^']+)')?")
_OPERAND: str = (
    r"(?:TIMESTAMP\s+'[^']*'|DATE\s+'[^']*'|'(?:[^']|'')*'|-?\d+(?:\.\d+)?|"
    r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)"
)
_BINARY: re.Pattern[str] = re.compile(
    rf"(?P<left>{_OPERAND})\s*(?:>=|<=|<>|!=|=|>|<|\+|\*|/|-)\s*(?P<right>{_OPERAND})",
    re.IGNORECASE,
)


def sentence_message(message: str) -> str:
    text: str = re.sub(r" \(context: [^)]*\)$", "", message)
    pieces: list[str] = re.split(r"('[^']*')", text)
    for index in range(0, len(pieces), 2):
        pieces[index] = re.sub(
            _TYPE_WORDS, lambda match: match.group().upper(), pieces[index], flags=re.IGNORECASE
        )
    return "".join(pieces)


def column_distance(*, left: str, right: str) -> int:
    """Levenshtein distance, also used to order schema evidence."""
    left, right = left.casefold(), right.casefold()
    row: list[int] = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        following: list[int] = [i]
        for j, b in enumerate(right, 1):
            following.append(min(following[-1] + 1, row[j] + 1, row[j - 1] + (a != b)))
        row = following
    return row[-1]


def ordered_columns(*, name: str, columns: dict[str, str]) -> list[str]:
    return sorted(
        columns,
        key=lambda value: (
            column_distance(left=name, right=value) / max(len(name), len(value), 1),
            value,
        ),
    )


def closest_column(*, name: str, columns: dict[str, str]) -> str | None:
    candidates: list[str] = ordered_columns(name=name, columns=columns)
    for candidate in candidates:
        distance: int = column_distance(left=name, right=candidate)
        remaining: Any = iter(candidate.casefold())
        abbreviation: bool = (
            len(name) >= _MIN_ABBREVIATION_LENGTH
            and candidate[:1].casefold() == name[:1].casefold()
            and candidate[-1:].casefold() == name[-1:].casefold()
            and all(character in remaining for character in name.casefold())
        )
        if distance <= _MAX_EDIT_DISTANCE or abbreviation:
            return candidate
    return None


def missing_column(message: str) -> tuple[str, str | None] | None:
    match: re.Match[str] | None = _MISSING.search(message)
    return (match.group(1), match.group(2)) if match else None


def input_aliases(*, model: CompiledModel, dialect: str | None) -> dict[str, str]:
    parsed: Any = _parsed_model(model=model, dialect=dialect)
    if parsed is None:
        return {}
    aliases: dict[str, set[str]] = {}
    for table in parsed.find_all("table"):
        value: dict[str, Any] = table.to_dict().get("table", {})
        name: str = str(value.get("name", {}).get("name", ""))
        aliases.setdefault(name, set()).add(name)
        alias: dict[str, Any] = value.get("alias") or {}
        if alias:
            aliases.setdefault(str(alias["name"]), set()).add(name)
    return {alias: next(iter(names)) for alias, names in aliases.items() if len(names) == 1}


def unaliased_output_columns(*, model: CompiledModel, dialect: str | None) -> set[str]:
    """Only an unaliased missing projection can lose its corrected output name."""
    parsed: Any = _parsed_model(model=model, dialect=dialect)
    if parsed is None:
        return set()
    projections: list[dict[str, Any]] = parsed.to_dict().get("select", {}).get("expressions", [])
    return {
        str(expression["column"]["name"]["name"])
        for expression in projections
        if _COLUMN_KIND in expression
    }


def _parsed_model(*, model: CompiledModel, dialect: str | None) -> Any:
    request: SqlSchemaValidationRequest = get_complete_schema_binding_request(
        query_sql=model.query_sql, placeholders=None, dialect=dialect, binding_schema={}
    )
    module: Any = import_polyglot_sql()
    try:
        return module.parse_one(request.sql, dialect=dialect)
    except module.PolyglotError:
        return None


def explain_diagnostics(project: CompiledProject) -> CompiledProject:
    """Enrich errors only; successful models require no extra SQL parsing."""
    if not project.diagnostics:
        return project
    shapes: dict[str, dict[str, str]] = semantic_shapes(project=project)
    models: dict[str, CompiledModel] = {model.name: model for model in project.models}
    aliases: dict[str, dict[str, str]] = {}
    diagnostics: list[CompilerDiagnostic] = []
    diagnostic: CompilerDiagnostic
    for diagnostic in project.diagnostics:
        model: CompiledModel | None = models.get(diagnostic.resource_name or "")
        if model is not None and diagnostic.code in {_UNKNOWN_COLUMN, *_TYPE_CODES}:
            if model.name not in aliases:
                aliases[model.name] = input_aliases(
                    model=model, dialect=project.sql_analysis_dialect
                )
            diagnostic = _explain_model(
                diagnostic=diagnostic,
                model=model,
                aliases=aliases[model.name],
                shapes=shapes,
                dialect=project.sql_analysis_dialect,
            )
        elif semantic_help(diagnostic.code) is not None:
            diagnostic = replace(
                diagnostic,
                message=sentence_message(diagnostic.message),
                help=semantic_help(diagnostic.code) or diagnostic.help,
            )
        diagnostics.append(diagnostic)
    return replace(
        project,
        diagnostics=tuple(diagnostics),
        models=update_binding_models(models=project.models, diagnostics=tuple(diagnostics)),
    )


def update_binding_models(
    *, models: tuple[CompiledModel, ...], diagnostics: tuple[CompilerDiagnostic, ...]
) -> tuple[CompiledModel, ...]:
    """Keep model binding facts distinct from metadata and SQL-test diagnostics."""
    by_model: dict[str, list[CompilerDiagnostic]] = {}
    for diagnostic in diagnostics:
        if diagnostic.resource_type == CompiledResourceType.MODEL:
            by_model.setdefault(diagnostic.resource_name or "", []).append(diagnostic)
    updated: list[CompiledModel] = []
    for model in models:
        codes: set[str] = {item.code for item in model.binding_diagnostics}
        bindings: tuple[CompilerDiagnostic, ...] = tuple(
            item for item in by_model.get(model.name, ()) if item.code in codes
        )
        updated.append(replace(model, binding_diagnostics=bindings))
    return tuple(updated)


def _explain_model(
    *,
    diagnostic: CompilerDiagnostic,
    model: CompiledModel,
    aliases: dict[str, str],
    shapes: dict[str, dict[str, str]],
    dialect: str | None,
) -> CompilerDiagnostic:
    message: str = sentence_message(diagnostic.message)
    help_text: str | None = semantic_help(diagnostic.code)
    if diagnostic.code == _COMPARISON:
        help_text = comparison_help(
            types=tuple(
                value.upper()
                for value in re.findall(_TYPE_WORDS, diagnostic.message, re.IGNORECASE)
            ),
            dialect=dialect,
        )
    notes: list[str] = list(diagnostic.notes)
    location: SourceLocation | None = diagnostic.location
    missing: tuple[str, str | None] | None = missing_column(diagnostic.message)
    if missing is not None:
        name, table = missing
        columns: dict[str, str] = shapes.get(table or "", {})
        suggestion: str | None = closest_column(name=name, columns=columns)
        help_text = f"did you mean '{suggestion}'?" if suggestion else None
        message = f"Unknown column '{name}'" + (f" in {table}" if table else "")
        if location is not None:
            lines: list[str] = model.authored_sql.splitlines()
            prefix: str = lines[location.line - 1][: location.column - 1]
            qualifier: re.Match[str] | None = re.search(
                r'(?:"((?:[^"]|"")+)"|([A-Za-z_]\w*))\.$', prefix
            )
            alias: str | None = (
                (qualifier.group(1) or qualifier.group(2)).replace('""', '"') if qualifier else None
            )
            if alias and aliases.get(alias) == table:
                message += f" (as {alias})"
        available: list[str] = ordered_columns(name=name, columns=columns)
        if available:
            suffix: str = (
                f", and {len(available) - _DISPLAY_LIMIT} more"
                if len(available) > _DISPLAY_LIMIT
                else ""
            )
            notes.insert(0, f"{table} has: {', '.join(available[:10])}{suffix}")
    if diagnostic.code in _TYPE_CODES and location is not None:
        offset: int = (
            sum(
                len(line)
                for line in model.authored_sql.splitlines(keepends=True)[: location.line - 1]
            )
            + location.column
            - 1
        )
        binary: re.Match[str] | None = next(
            (
                match
                for match in _BINARY.finditer(model.authored_sql)
                if match.start() <= offset < match.end()
            ),
            None,
        )
        if binary:
            left: str = binary.group("left")
            right: str = binary.group("right")
            types: tuple[str | None, str | None] = (
                _operand_type(text=left, aliases=aliases, shapes=shapes),
                _operand_type(text=right, aliases=aliases, shapes=shapes),
            )
            if all(types):
                notes.append(f"{left} is {types[0]}, {right} is {types[1]}")
                if diagnostic.code == _COMPARISON:
                    help_text = comparison_help(
                        types=tuple(value for value in types if value), dialect=dialect
                    )
            end: int = binary.end()
            if location.end_line is not None and location.end_column is not None:
                native_end: int = (
                    sum(
                        len(line)
                        for line in model.authored_sql.splitlines(keepends=True)[
                            : location.end_line - 1
                        ]
                    )
                    + location.end_column
                    - 1
                )
                end = max(end, native_end)
            begin: int = min(binary.start(), offset)
            location = replace(
                location,
                line=model.authored_sql.count("\n", 0, begin) + 1,
                column=begin - model.authored_sql.rfind("\n", 0, begin),
                end_line=model.authored_sql.count("\n", 0, end) + 1,
                end_column=end - model.authored_sql.rfind("\n", 0, end),
            )
        else:
            operand: re.Match[str] | None = re.compile(_OPERAND, re.IGNORECASE).match(
                model.authored_sql, offset
            )
            if operand:
                operand_type: str | None = _operand_type(
                    text=operand.group(), aliases=aliases, shapes=shapes
                )
                if operand_type:
                    notes.append(f"{operand.group()} is {operand_type}")
    return replace(
        diagnostic,
        message=message,
        help=help_text,
        notes=tuple(notes),
        location=location,
        line=location.line if location is not None else diagnostic.line,
        column=location.column if location is not None else diagnostic.column,
    )


def _operand_type(
    *, text: str, aliases: dict[str, str], shapes: dict[str, dict[str, str]]
) -> str | None:
    temporal: re.Match[str] | None = re.match(r"(TIMESTAMP|DATE)\s*'", text, re.IGNORECASE)
    if temporal:
        return temporal.group(1).upper()
    if re.fullmatch(r"-?\d+", text):
        return "INTEGER"
    if re.fullmatch(r"-?\d+\.\d+", text):
        return "DECIMAL"
    if text.startswith("'"):
        return "VARCHAR"
    if _QUALIFIER_SEPARATOR in text:
        alias, column = text.split(".", 1)
        value: str | None = shapes.get(aliases.get(alias, alias), {}).get(column)
        return value.upper() if value else None
    candidates: set[str] = {
        shapes[table][text].upper()
        for table in set(aliases.values())
        if table in shapes and text in shapes[table]
    }
    return next(iter(candidates)) if len(candidates) == 1 else None
