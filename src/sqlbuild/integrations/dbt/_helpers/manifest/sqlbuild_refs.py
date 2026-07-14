"""Helpers for SQLBuild model references into dbt manifests."""

from __future__ import annotations

from collections.abc import Sequence

from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.integrations.dbt._helpers.manifest.core import resolve_dbt_manifest_model
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex, DbtManifestModel


def resolve_sqlbuild_model_dbt_refs(
    *,
    project: CompiledProject,
    manifest: DbtManifestIndex,
    selected_model_names: Sequence[str] | None = None,
) -> tuple[tuple[CompiledModel, DbtManifestModel], ...]:
    """Return resolved dbt refs used directly by SQLBuild models."""

    selected_names: frozenset[str] | None = (
        None if selected_model_names is None else frozenset(selected_model_names)
    )
    refs: list[tuple[CompiledModel, DbtManifestModel]] = []
    model: CompiledModel
    for model in project.models:
        if selected_names is not None and model.name not in selected_names:
            continue
        for reference in model.references:
            if reference.ref_kind != SqlReferenceKind.DBT_REF:
                continue
            refs.append(
                (
                    model,
                    resolve_dbt_manifest_model(
                        manifest=manifest,
                        package_name=reference.ref_package,
                        name=reference.ref_name,
                    ),
                )
            )
    return tuple(refs)


def resolve_dbt_reference_relation(
    *,
    manifest: DbtManifestIndex | None,
    ref_kind: str,
    ref_name: str,
    ref_package: str | None,
) -> str | None:
    """Resolve one external dbt reference to its manifest relation."""

    if ref_kind != SqlReferenceKind.DBT_REF or manifest is None:
        return None
    return resolve_dbt_manifest_model(
        manifest=manifest,
        package_name=ref_package,
        name=ref_name,
    ).relation_name
