"""Typed, metadata-preserving repository edits for contract adoption."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledModel, CompiledSource
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.contract_adoption._helpers.repository_edits import (
    edit_model,
    edit_source,
    remaining_findings,
)
from sqlbuild.compiler.contract_adoption.models import (
    ContractAdoptionResult,
    ContractEvidence,
    ContractFinding,
)
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.lint.main.write_atomically import write_atomically


def write_contracts(
    *,
    project_dir: Path,
    graph: ProjectGraph,
    result: ContractAdoptionResult,
    overwrite: bool,
    adapter: BaseAdapter | None = None,
    cli_vars: dict[str, object] | None = None,
) -> ContractAdoptionResult:
    """Apply safe source-only edits atomically and validate the resulting project."""

    models: dict[str, CompiledModel] = {model.name: model for model in graph.project.models}
    sources: dict[str, CompiledSource] = {source.name: source for source in graph.project.sources}
    updates: dict[Path, str] = {}
    updated_evidence: list[ContractEvidence] = []
    for evidence in result.evidence:
        if evidence.physical_columns is None or not evidence.findings:
            updated_evidence.append(evidence)
            continue
        if evidence.resource_type == CompiledResourceType.MODEL:
            contents, conflict = edit_model(
                model=models[evidence.resource_name],
                physical_columns=evidence.physical_columns,
                overwrite=overwrite,
            )
            path: Path = project_dir / models[evidence.resource_name].relative_path
        else:
            path = sources[evidence.resource_name].source_file.file_path
            contents, conflict = edit_source(
                source=sources[evidence.resource_name],
                physical_columns=evidence.physical_columns,
                overwrite=overwrite,
                contents=updates.get(path),
            )
        if contents is not None and contents != path.read_text(encoding="utf-8"):
            updates[path] = contents
        remaining: tuple[ContractFinding, ...] = remaining_findings(
            findings=evidence.findings,
            overwrite=overwrite,
            conflict=conflict,
        )
        updated_evidence.append(replace(evidence, findings=remaining))
    if not updates:
        return replace(result, evidence=tuple(updated_evidence))
    originals: dict[Path, str] = {path: path.read_text(encoding="utf-8") for path in updates}
    try:
        for path, contents in updates.items():
            write_atomically(path=path, contents=contents)
        discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
        if adapter is not None:
            _ = build_project_graph(
                discovered_inputs=discovered,
                adapter=adapter,
                selected_target=result.from_target,
                cli_vars=cli_vars,
                no_cache=True,
            )
    except Exception:
        for path, contents in originals.items():
            write_atomically(path=path, contents=contents)
        raise
    return replace(
        result,
        evidence=tuple(updated_evidence),
        written_paths=tuple(sorted(path.relative_to(project_dir) for path in updates)),
    )
