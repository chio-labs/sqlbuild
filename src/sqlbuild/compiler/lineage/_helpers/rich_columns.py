"""Rich column lineage glue: the analysis dialect name and the project graph assembly."""

from __future__ import annotations

from sqlbuild.adapter.contract.types import BuiltinAdapter, TypeDialect
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.lineage.models import (
    ColumnLineageEdge,
    ModelColumnLineage,
    ProjectColumnLineage,
    QualifiedLineageColumn,
)
from sqlbuild.compiler.lineage.types import PolyglotAnalysisDialect

_POLYGLOT_DIALECT_ALIASES: dict[str, PolyglotAnalysisDialect] = {
    "": PolyglotAnalysisDialect.GENERIC,
    "ansi": PolyglotAnalysisDialect.GENERIC,
    "generic": PolyglotAnalysisDialect.GENERIC,
    TypeDialect.GENERIC.value: PolyglotAnalysisDialect.GENERIC,
    TypeDialect.BIGQUERY.value: PolyglotAnalysisDialect.BIGQUERY,
    TypeDialect.SNOWFLAKE.value: PolyglotAnalysisDialect.SNOWFLAKE,
    TypeDialect.DUCKDB.value: PolyglotAnalysisDialect.DUCKDB,
    TypeDialect.MOTHERDUCK.value: PolyglotAnalysisDialect.DUCKDB,
    TypeDialect.DATABRICKS.value: PolyglotAnalysisDialect.DATABRICKS,
    TypeDialect.POSTGRES.value: PolyglotAnalysisDialect.POSTGRESQL,
    TypeDialect.TSQL.value: PolyglotAnalysisDialect.TSQL,
    BuiltinAdapter.SQLSERVER.value: PolyglotAnalysisDialect.TSQL,
    "postgresql": PolyglotAnalysisDialect.POSTGRESQL,
}


def assemble_rich_project_column_lineage(
    model_results: dict[str, ModelColumnLineage],
) -> ProjectColumnLineage:
    """Collapse per-model rich lineage, in model order, into the project graph and its edges."""

    collapsed_edges: list[ColumnLineageEdge] = []
    for target_resource_name, result in model_results.items():
        for column in result.columns:
            target: QualifiedLineageColumn = QualifiedLineageColumn(
                resource_type=CompiledResourceType.MODEL,
                resource_name=target_resource_name,
                column_name=column.output_column,
            )
            for upstream in column.upstream_columns:
                collapsed_edges.append(
                    ColumnLineageEdge(
                        source=upstream.as_qualified_column(),
                        target=target,
                        transform_kind=column.transform_kind,
                        confidence=column.confidence,
                    )
                )

    return ProjectColumnLineage(models=model_results, edges=tuple(collapsed_edges))


def _polyglot_dialect(dialect: str | TypeDialect | None) -> PolyglotAnalysisDialect:
    if dialect is None:
        return PolyglotAnalysisDialect.GENERIC
    normalized: str = dialect.strip().lower()
    mapped: PolyglotAnalysisDialect | None = _POLYGLOT_DIALECT_ALIASES.get(normalized)
    if mapped is not None:
        return mapped
    return PolyglotAnalysisDialect(normalized)
