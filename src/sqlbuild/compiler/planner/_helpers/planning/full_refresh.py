"""Per-model full-refresh resolution."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject


def resolve_model_full_refresh(*, model: CompiledModel, cli_full_refresh: bool) -> bool:
    """Resolve dbt-compatible nullable model full-refresh semantics."""

    configured: object | None = model.config.values.get("full_refresh")
    return configured if isinstance(configured, bool) else cli_full_refresh


def effectively_full_refreshed_model_names(
    *, project: CompiledProject, cli_full_refresh: bool
) -> frozenset[str]:
    """Return model names that are effectively full refreshed for this invocation."""

    return frozenset(
        model.name
        for model in project.models
        if resolve_model_full_refresh(model=model, cli_full_refresh=cli_full_refresh)
    )
