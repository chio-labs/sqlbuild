"""Resolve the dbt manifest path."""

from pathlib import Path

from sqlbuild.integrations.dbt.helpers.planning.runtime import resolve_dbt_manifest_path as _resolve
from sqlbuild.integrations.dbt.models import DbtCliOptions


def resolve_dbt_manifest_path(*, options: DbtCliOptions) -> Path:
    """Resolve the manifest path produced by dbt compile."""

    return _resolve(options=options)
