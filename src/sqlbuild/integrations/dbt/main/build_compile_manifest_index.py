"""Public dbt compile manifest index entrypoint."""

from __future__ import annotations

from sqlbuild.integrations.dbt.helpers.compile_refs import build_compile_dbt_manifest_index
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex


def build_compile_manifest_index(*, manifest_contents: str | None) -> DbtManifestIndex | None:
    """Build a dbt manifest index from discovered manifest contents."""

    return build_compile_dbt_manifest_index(manifest_contents=manifest_contents)
