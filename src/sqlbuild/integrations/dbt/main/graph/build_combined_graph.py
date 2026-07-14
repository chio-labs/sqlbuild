"""Build the combined dbt and SQLBuild graph."""

from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.integrations.dbt.helpers.graph.core import build_dbt_combined_graph as _build
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import DbtCombinedGraph


def build_dbt_combined_graph(
    *, manifest: DbtManifestIndex, project: CompiledProject
) -> DbtCombinedGraph:
    """Build the combined dbt and SQLBuild graph."""

    return _build(manifest=manifest, project=project)
