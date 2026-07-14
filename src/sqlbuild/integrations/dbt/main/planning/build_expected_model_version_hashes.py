"""Build expected dbt model version hashes."""

from sqlbuild.integrations.dbt._helpers.planning.model_planning import (
    build_expected_dbt_model_version_hashes as _build,
)
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import DbtCombinedGraph


def build_expected_dbt_model_version_hashes(
    *, manifest: DbtManifestIndex, graph: DbtCombinedGraph | None
) -> dict[str, str | None]:
    """Build expected version hashes for dbt models."""

    return _build(manifest=manifest, graph=graph)
