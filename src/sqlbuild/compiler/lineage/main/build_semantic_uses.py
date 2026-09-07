"""Build on-demand direct non-projection semantic column uses."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.lineage._helpers.columns import _build_schema_mapping
from sqlbuild.compiler.lineage._helpers.semantic_uses import get_model_semantic_uses
from sqlbuild.compiler.lineage.models import DirectSemanticColumnUse


def build_direct_semantic_uses(
    *, project: CompiledProject, dialect: str | None, model_names: frozenset[str]
) -> tuple[DirectSemanticColumnUse, ...]:
    """Extract semantic uses only for explicitly requested models."""

    schema: dict[str, dict[str, str]] = _build_schema_mapping(project)
    uses: list[DirectSemanticColumnUse] = []
    for model in project.models:
        if model.name not in model_names:
            continue
        uses.extend(get_model_semantic_uses(model=model, schema=schema, dialect=dialect))
    return tuple(uses)
