"""CLI dag command entry point."""

from __future__ import annotations

import json
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild._native import discover_project_inputs
from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.planning.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.cli.commands._helpers.runtime.adapters import resolve_adapter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.python_nodes.main.graph import build_discovered_python_node_graph
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)


def run_dag(
    *,
    project_dir: Path | None,
    no_sql_validation: bool = False,
    json_output: bool = False,
    cli_vars: dict[str, object] | None = None,
) -> int:
    """Execute the dag command."""

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    adapter: BaseAdapter = resolve_adapter(
        adapter_name=resolve_effective_adapter_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        ),
        project_dir=effective_project_dir,
    )
    graph: ProjectGraph = _native.build_project_graph(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        cli_vars=cli_vars,
        external_sql_reference_resolver=resolve_external_sql_reference_resolver(
            project_dir=effective_project_dir,
            discovered_inputs=discovered_inputs,
        ),
    )
    python_graph: PythonNodeGraph = build_discovered_python_node_graph(
        discovered_inputs=discovered_inputs
    )
    dag_json: str = _native.build_dag_json(
        graph=graph,
        project_name=discovered_inputs.project_config.name,
        python_graph=python_graph,
    )
    if json_output:
        print(dag_json)
    else:
        payload: dict[str, object] = json.loads(dag_json)
        print(
            "DAG ready "
            f"({len(payload['nodes'])} nodes, {len(payload['edges'])} edges, "
            f"{len(payload['checks'])} checks)"
        )
    return 0
