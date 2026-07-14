"""Inspect combined graph clone eligibility."""

from sqlbuild.integrations.dbt.helpers.graph.core import combined_graph_node_is_clonable as _check
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import DbtCombinedGraphKey


def combined_graph_node_is_clonable(
    *, key: DbtCombinedGraphKey, manifest: DbtManifestIndex
) -> bool:
    """Return whether a combined graph node can be cloned."""

    return _check(key=key, manifest=manifest)
