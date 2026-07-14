"""Resolve dbt manifest model materialization."""

from sqlbuild.integrations.dbt.helpers.manifest.core import (
    dbt_manifest_model_materialization as _resolve,
)
from sqlbuild.integrations.dbt.manifest.models import DbtManifestModel


def dbt_manifest_model_materialization(*, model: DbtManifestModel) -> str | None:
    """Return a manifest model's normalized materialization."""

    return _resolve(model=model)
