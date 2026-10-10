"""Reference analysis names, lineage resource types, qualified-reference scans and placeholders."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import (
    CompileSqlReference,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.sql_analysis.main._normalize_analysis import normalize_analysis_sql


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
    return _native.substitute_placeholder_defaults(query_sql, list(placeholders.items()))


def _replace_refs_with_stubs(
    *,
    query_sql: str,
    dialect: str | None = None,
    relation_stubs: dict[str, str] | None = None,
) -> str:
    """Replace SQLBuild marker calls with parseable SQL stubs."""

    return normalize_analysis_sql(sql=query_sql, dialect=dialect, stubs=relation_stubs)
