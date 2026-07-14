"""Inspect combined graph view materialization."""

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.integrations.dbt._helpers.graph.core import combined_graph_node_is_view as _check
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import DbtCombinedGraphKey


def combined_graph_node_is_view(
    *, key: DbtCombinedGraphKey, manifest: DbtManifestIndex, project: CompiledProject
) -> bool:
    """Return whether a combined graph node is a view."""

    return _check(key=key, manifest=manifest, project=project)
