"""Virtual-mode Python node plan-entry entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.pipeline.main.python_plan_entries import build_python_plan_entries
from sqlbuild.compiler.pipeline.models import PythonPlanEntry
from sqlbuild.compiler.python_nodes.main.graph import build_discovered_python_node_graph
from sqlbuild.compiler.python_nodes.main.run_lifecycle import build_python_sql_run_lifecycle
from sqlbuild.compiler.python_nodes.models import (
    PythonNodeGraph,
    PythonSqlRunLifecyclePlan,
    PythonSqlRunSelection,
)


def build_virtual_python_plan_entries(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    selection: PythonSqlRunSelection,
    previous_identities: dict[tuple[str, str], Fingerprint] | None = None,
) -> tuple[PythonPlanEntry, ...]:
    """Return display entries for a virtual Python selection."""

    python_graph: PythonNodeGraph = build_discovered_python_node_graph(
        discovered_inputs=discovered_inputs
    )
    lifecycle_plan: PythonSqlRunLifecyclePlan = build_python_sql_run_lifecycle(
        selection=selection,
        python_graph=python_graph,
    )
    return build_python_plan_entries(
        lifecycle_plan=lifecycle_plan,
        python_graph=python_graph,
        previous_identities=previous_identities,
    )
