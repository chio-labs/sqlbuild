"""Public compile-time resolved column-read analysis operation."""

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import (
    CompiledLineageSourceFact,
    CompileSqlReference,
)


def analyze_resolved_column_reads(
    *,
    query_sql: str,
    references: tuple[CompileSqlReference, ...],
    dialect: str | None,
) -> tuple[CompiledLineageSourceFact, ...]:
    """Return CTE-aware column reads resolved to external resources."""

    reference_rows: list[tuple[str, str]] = [
        (str(reference.ref_kind), reference.ref_name) for reference in references
    ]
    reads: list[tuple[str, str, str]] = _native.resolve_required_columns(
        query_sql, reference_rows, dialect
    )
    return tuple(
        CompiledLineageSourceFact(
            resource_type=resource_type, resource_name=resource_name, column_name=column_name
        )
        for resource_type, resource_name, column_name in reads
    )
