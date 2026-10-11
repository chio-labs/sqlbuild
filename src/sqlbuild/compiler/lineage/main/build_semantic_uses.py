"""Build on-demand direct non-projection semantic column uses."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.compiler.compile.types import CompiledProjectView, CompiledResourceType
from sqlbuild.compiler.lineage._helpers.native_rich_columns import _schema_resources
from sqlbuild.compiler.lineage.models import DirectSemanticColumnUse, QualifiedLineageColumn
from sqlbuild.compiler.lineage.types import ColumnLineageConfidence, NativeSemanticUseRow


def build_direct_semantic_uses(
    *, project: CompiledProjectView, dialect: str | None, model_names: frozenset[str]
) -> tuple[DirectSemanticColumnUse, ...]:
    """Extract semantic uses only for explicitly requested models."""

    rows: list[NativeSemanticUseRow] = _native.build_direct_semantic_uses(
        _schema_resources(project),
        [
            (model.name, model.query_sql, model.authored_sql)
            for model in project.models
            if model.name in model_names
        ],
        dialect or "generic",
    )
    return tuple(
        DirectSemanticColumnUse(
            consumer_model=model,
            context=context,
            expression_sql=expression,
            source=QualifiedLineageColumn(
                resource_type=CompiledResourceType(kind),
                resource_name=resource,
                column_name=column,
            ),
            confidence=ColumnLineageConfidence(confidence),
            line=line,
            column=offset,
        )
        for model, context, expression, kind, resource, column, confidence, line, offset in rows
    )
