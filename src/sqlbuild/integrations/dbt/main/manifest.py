"""Public dbt manifest entrypoints."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.integrations.dbt.helpers.manifest import (
    load_dbt_manifest_index,
)
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex


def load_manifest_index(*, manifest_path: Path) -> DbtManifestIndex:
    """Load and index a dbt manifest file."""

    return load_dbt_manifest_index(manifest_path=manifest_path)
