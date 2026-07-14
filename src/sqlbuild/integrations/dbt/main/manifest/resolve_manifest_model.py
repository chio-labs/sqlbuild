"""Public dbt manifest model resolution entrypoint."""

from __future__ import annotations

from sqlbuild.integrations.dbt.helpers.manifest.core import (
    resolve_dbt_manifest_model as _resolve_dbt_manifest_model,
)
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex, DbtManifestModel


def resolve_manifest_model(
    *, manifest: DbtManifestIndex, name: str, package_name: str | None = None
) -> DbtManifestModel:
    """Resolve a dbt model from a manifest index."""

    return _resolve_dbt_manifest_model(
        manifest=manifest,
        name=name,
        package_name=package_name,
    )
