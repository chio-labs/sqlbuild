"""Public dbt manifest indexing entrypoint."""

from __future__ import annotations

from sqlbuild.integrations.dbt.helpers.manifest import (
    build_dbt_manifest_index as _build_dbt_manifest_index,
)
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex


def build_manifest_index(*, raw_data: object) -> DbtManifestIndex:
    """Build a dbt manifest index from decoded manifest JSON."""

    return _build_dbt_manifest_index(raw_data=raw_data)
