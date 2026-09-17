"""Public compile-time resolved column-read analysis operation."""

from sqlbuild.compiler.compile._helpers.analysis.required_columns import (
    resolve_required_external_columns,
)
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

    return resolve_required_external_columns(
        query_sql=query_sql,
        references=references,
        dialect=dialect,
    )
