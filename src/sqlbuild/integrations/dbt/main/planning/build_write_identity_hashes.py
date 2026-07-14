"""Build dbt write identity hashes."""

from sqlbuild.compiler.planner.models import GraphNodeKey
from sqlbuild.integrations.dbt._helpers.planning.model_identity import (
    build_dbt_write_identity_hashes as _build,
)
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import DbtCombinedGraph


def build_dbt_write_identity_hashes(
    *,
    manifest: DbtManifestIndex,
    graph: DbtCombinedGraph | None,
    run_unique_ids: frozenset[str],
    expected_version_hash_by_unique_id: dict[str, str | None],
    previous_version_hash_by_unique_id: dict[str, str] | None = None,
) -> dict[GraphNodeKey, str]:
    """Build version hashes recorded for dbt nodes in one run."""

    return _build(
        manifest=manifest,
        graph=graph,
        run_unique_ids=run_unique_ids,
        expected_version_hash_by_unique_id=expected_version_hash_by_unique_id,
        previous_version_hash_by_unique_id=previous_version_hash_by_unique_id,
    )
