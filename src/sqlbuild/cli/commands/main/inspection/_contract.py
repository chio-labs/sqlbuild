"""Contract comparison and repository adoption command."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlbuild.cli.commands._helpers.runtime.adapter_context import (
    resolve_adapter_connection_context,
)
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.cli.commands.models import AdapterConnectionContext, ContractCommandRequest
from sqlbuild.compiler.compile.models import CompiledModel, CompiledObjectKey, CompiledSource
from sqlbuild.compiler.contract_adoption.main.compare import compare_contracts
from sqlbuild.compiler.contract_adoption.models import ContractAdoptionResult, ContractEvidence
from sqlbuild.compiler.contract_adoption.types import ContractAction
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.main.selection.selection import (
    resolve_project_selectors,
)


def run_contract(request: ContractCommandRequest) -> int:
    """Compare or adopt selected contracts from one read-only target."""

    if request.overwrite and (request.action != ContractAction.GENERATE or not request.write):
        raise CliUserError("contract --overwrite requires generate --write", code="C471")
    project_dir: Path = request.project_dir or Path.cwd()
    discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    if request.from_target not in discovered.project_config.targets:
        raise CliUserError(
            f"unknown contract source target '{request.from_target}'",
            code="C472",
        )
    context: AdapterConnectionContext = resolve_adapter_connection_context(
        discovered_inputs=discovered,
        effective_project_dir=project_dir,
        selected_target=None,
        cli_vars=request.cli_vars,
    )
    graph: ProjectGraph = build_project_graph(
        discovered_inputs=discovered,
        adapter=context.adapter,
        selected_target=request.from_target,
        cli_vars=request.cli_vars,
        no_cache=True,
    )
    selected: frozenset[CompiledObjectKey] = resolve_project_selectors(
        select=request.select,
        exclude=request.exclude,
        all_keys=graph.all_keys,
        upstream_deps=graph.upstream_deps,
        downstream_deps=graph.downstream_deps,
        tag_index=graph.tag_index,
        path_index=graph.path_index,
    )
    selected_models: tuple[CompiledModel, ...] = tuple(
        model for model in graph.project.models if model.key in selected
    )
    selected_sources: tuple[CompiledSource, ...] = tuple(
        source for source in graph.project.sources if source.key in selected
    )
    if not selected_models and not selected_sources:
        raise CliUserError("contract selection contains no models or sources", code="C473")
    connection: Any = context.adapter.connect(context.connection_config)
    try:
        evidence: tuple[ContractEvidence, ...] = compare_contracts(
            adapter=context.adapter,
            connection=connection,
            models=selected_models,
            sources=selected_sources,
        )
    finally:
        context.adapter.close(connection)
    result: ContractAdoptionResult = ContractAdoptionResult(
        from_target=request.from_target, evidence=evidence
    )
    if request.action == ContractAction.GENERATE and request.write:
        from sqlbuild.compiler.contract_adoption.main.write import write_contracts

        result = write_contracts(
            project_dir=project_dir,
            graph=graph,
            result=result,
            overwrite=request.overwrite,
            adapter=context.adapter,
            cli_vars=request.cli_vars,
        )
    _write_output(request=request, result=result)
    return 1 if result.findings else 0


def _write_output(*, request: ContractCommandRequest, result: ContractAdoptionResult) -> None:
    if request.json_output:
        print(
            json.dumps(
                _result_json_payload(result=result),
                indent=2,
                sort_keys=True,
            )
        )
        return
    print(f"Contract comparison from target '{result.from_target}'")
    for item in result.evidence:
        label: str = f"{item.resource_type.value}:{item.resource_name}"
        if not item.findings:
            print(f"  OK    {label}")
            continue
        print(f"  DIFF  {label}")
        for finding in item.findings:
            print(f"        {finding.kind.value}: {finding.message}")
    if result.written_paths:
        print("\nUpdated repository declarations:")
        for path in result.written_paths:
            print(f"  {path}")
    print(f"\n{len(result.findings)} contract difference(s)")


def _result_json_payload(*, result: ContractAdoptionResult) -> dict[str, object]:
    resources: list[dict[str, object]] = []
    for item in result.evidence:
        findings: list[dict[str, object]] = []
        for finding in item.findings:
            findings.append(
                {
                    "kind": str(finding.kind),
                    "column": finding.column_name,
                    "declared_type": finding.declared_type,
                    "physical_type": finding.physical_type,
                    "message": finding.message,
                }
            )
        resources.append(
            {
                "resource_type": str(item.resource_type),
                "resource_name": item.resource_name,
                "relation": ".".join(
                    value for value in (item.database, item.schema, item.relation) if value
                ),
                "findings": findings,
            }
        )
    return {
        "from_target": result.from_target,
        "differences": len(result.findings),
        "written_paths": [str(path) for path in result.written_paths],
        "resources": resources,
    }
