"""Public dbt source freshness translation entrypoint."""

from __future__ import annotations

from sqlbuild.integrations.dbt._helpers.runtime.source_freshness import (
    translate_manifest_sources_to_sqlbuild_sources,
)
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.spec.contracts.models import SourceEntry


def translate_dbt_manifest_sources_to_sqlbuild_sources(
    *, manifest: DbtManifestIndex
) -> tuple[SourceEntry, ...]:
    """Translate dbt manifest source nodes to SQLBuild source entries."""

    return translate_manifest_sources_to_sqlbuild_sources(manifest=manifest)
