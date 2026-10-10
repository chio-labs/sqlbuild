"""Reference analysis names, lineage resource types, qualified-reference scans and placeholders."""

from __future__ import annotations

import re
from collections.abc import Iterable

from sqlbuild.compiler.compile.constants import (
    SQL_QUALIFIER_SEPARATOR_TOKEN,
)
from sqlbuild.compiler.compile.models import (
    CompileSqlReference,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.sql_analysis.main._normalize_analysis import normalize_analysis_sql

_PLACEHOLDER_PATTERN: re.Pattern[str] = re.compile(r"@@@(\w+)")
_QUALIFIED_IDENTIFIER_PATTERN: re.Pattern[str] = re.compile(
    r'(?<![A-Za-z0-9_$])(?:"(?P<double>[^"]+)"|`(?P<backtick>[^`]+)`|'
    r"\[(?P<bracket>[^\]]+)\]|(?P<plain>[A-Za-z_$][A-Za-z0-9_$]*))"
    r"(?:\s|--[^\r\n]*(?:\r?\n|$)|/\*.*?\*/)*\.",
    re.DOTALL,
)
_QUALIFIED_SCAN_CONSUMING_TOKENS: tuple[str, ...] = ('"', "`", "[", "--", "/*")
_PLAIN_IDENTIFIER_PATTERN: re.Pattern[str] = re.compile(r"[a-z_$][a-z0-9_$]*")
_IDENTIFIER_CHARACTERS: frozenset[str] = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$"
)


def _lineage_resource_type(reference: CompileSqlReference) -> CompiledResourceType | None:
    if reference.ref_kind == SqlReferenceKind.REF:
        return CompiledResourceType.MODEL
    if reference.ref_kind == SqlReferenceKind.SOURCE:
        return CompiledResourceType.SOURCE
    if reference.ref_kind == SqlReferenceKind.SEED:
        return CompiledResourceType.SEED
    if reference.ref_kind == SqlReferenceKind.TABLE_FUNCTION:
        return CompiledResourceType.TABLE_FN
    return None


def _analysis_reference_name(reference: CompileSqlReference) -> str:
    if reference.ref_kind == SqlReferenceKind.TABLE_FUNCTION:
        return table_function_analysis_name(reference.ref_name)
    return reference.ref_name


def table_function_analysis_name(function_name: str) -> str:
    """Return the stable relation stub used to analyze a table-function call."""

    return f"__sqlbuild_table_function_{function_name}"


def substitute_placeholder_defaults(*, query_sql: str, placeholders: dict[str, str]) -> str:
    """Replace @@@name tokens with their default values for SQL analysis parsing."""

    if not placeholders:
        return query_sql

    def _replacer(match: re.Match[str]) -> str:
        name: str = match.group(1)
        return placeholders.get(name, match.group(0))

    return _PLACEHOLDER_PATTERN.sub(_replacer, query_sql)


def _replace_refs_with_stubs(
    *,
    query_sql: str,
    dialect: str | None = None,
    relation_stubs: dict[str, str] | None = None,
) -> str:
    """Replace SQLBuild marker calls with parseable SQL stubs."""

    return normalize_analysis_sql(sql=query_sql, dialect=dialect, stubs=relation_stubs)


def _qualified_reference_names(*, query_sql: str, reference_names: Iterable[str]) -> frozenset[str]:
    """Return qualifier reference names, searching names directly when no token can hide one."""

    if SQL_QUALIFIER_SEPARATOR_TOKEN not in query_sql:
        return frozenset()
    names_by_normalized: dict[str, list[str]] = {}
    for value in reference_names:
        name: str = str(value)
        names_by_normalized.setdefault(name.casefold(), []).append(name)
    if not names_by_normalized:
        return frozenset()
    if not query_sql.isascii() or any(
        token in query_sql for token in _QUALIFIED_SCAN_CONSUMING_TOKENS
    ):
        return _scanned_qualified_reference_names(
            query_sql=query_sql, names_by_normalized=names_by_normalized
        )

    folded_sql: str = query_sql.lower()
    qualified: set[str] = set()
    for normalized, names in names_by_normalized.items():
        if _PLAIN_IDENTIFIER_PATTERN.fullmatch(normalized) is not None and _is_qualifier(
            folded_sql=folded_sql, name=normalized
        ):
            qualified.update(names)
    return frozenset(qualified)


def _is_qualifier(*, folded_sql: str, name: str) -> bool:
    length: int = len(folded_sql)
    start: int = folded_sql.find(name)
    while start != -1:
        end: int = start + len(name)
        if (start == 0 or folded_sql[start - 1] not in _IDENTIFIER_CHARACTERS) and (
            end == length or folded_sql[end] not in _IDENTIFIER_CHARACTERS
        ):
            while end < length and folded_sql[end].isspace():
                end += 1
            if end < length and folded_sql[end] == SQL_QUALIFIER_SEPARATOR_TOKEN:
                return True
        start = folded_sql.find(name, start + 1)
    return False


def _scanned_qualified_reference_names(
    *, query_sql: str, names_by_normalized: dict[str, list[str]]
) -> frozenset[str]:
    qualified: set[str] = set()
    for match in _QUALIFIED_IDENTIFIER_PATTERN.finditer(query_sql):
        identifier: str = next(value for value in match.groups() if value is not None)
        qualified.update(names_by_normalized.get(identifier.casefold(), ()))
    return frozenset(qualified)
