"""Resolve SQLBuild model references to dbt models."""

from collections.abc import Sequence

from sqlbuild.compiler.compile.types import CompiledModelView, CompiledProjectView
from sqlbuild.integrations.dbt._helpers.manifest.sqlbuild_refs import (
    resolve_sqlbuild_model_dbt_refs as _resolve,
)
from sqlbuild.integrations.dbt.models import DbtManifestIndex, DbtManifestModel


def resolve_sqlbuild_model_dbt_refs(
    *,
    project: CompiledProjectView,
    manifest: DbtManifestIndex,
    selected_model_names: Sequence[str] | None = None,
) -> tuple[tuple[CompiledModelView, DbtManifestModel], ...]:
    """Return dbt refs used directly by SQLBuild models."""

    return _resolve(project=project, manifest=manifest, selected_model_names=selected_model_names)
