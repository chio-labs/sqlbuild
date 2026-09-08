"""Lifecycle progress for contract inspection and repository updates."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, TextIO

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands.models import AdapterConnectionContext, ContractCommandRequest
from sqlbuild.cli.progress.classes.connection_progress_reporter import (
    ConnectionProgressReporter,
)
from sqlbuild.compiler.compile.models import CompiledModel, CompiledSource
from sqlbuild.compiler.contract_adoption.main.compare import compare_contracts
from sqlbuild.compiler.contract_adoption.models import ContractAdoptionResult, ContractEvidence
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.presentation.classes.transient_status_reporter import TransientStatusReporter


def inspect_contracts_with_progress(
    *,
    context: AdapterConnectionContext,
    request: ContractCommandRequest,
    selected_models: tuple[CompiledModel, ...],
    selected_sources: tuple[CompiledSource, ...],
    progress_stream: TextIO,
    use_progress_color: bool,
) -> tuple[ContractEvidence, ...]:
    """Connect once and report contract inspection lifecycle progress."""

    connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=context.adapter_name,
        stream=progress_stream,
        use_color=use_progress_color,
    )
    connection_started: float = time.monotonic()
    connection_progress.on_connection_start(1)
    try:
        connection: Any = context.adapter.connect(context.connection_config)
    except Exception:
        connection_progress.on_connection_error(
            connection_count=1,
            elapsed_seconds=time.monotonic() - connection_started,
        )
        raise
    try:
        connection_progress.on_connection_complete(
            connection_count=1,
            elapsed_seconds=time.monotonic() - connection_started,
        )

        resource_count: int = len(selected_models) + len(selected_sources)
        resource_label: str = "contract" if resource_count == 1 else "contracts"
        inspection_progress: TransientStatusReporter = TransientStatusReporter(
            stream=progress_stream,
            use_color=use_progress_color,
        )
        inspection_started: float = time.monotonic()
        inspection_progress.start(
            f"Inspecting {resource_count} {resource_label} from target '{request.from_target}'..."
        )
        try:
            evidence: tuple[ContractEvidence, ...] = compare_contracts(
                adapter=context.adapter,
                connection=connection,
                models=selected_models,
                sources=selected_sources,
            )
        except Exception:
            inspection_progress.error(
                f"Contract inspection failed after {time.monotonic() - inspection_started:.2f}s"
            )
            raise
        inspection_progress.complete(
            message=(
                f"Inspected {resource_count} {resource_label} from target "
                f"'{request.from_target}' ({time.monotonic() - inspection_started:.2f}s)"
            )
        )
    finally:
        context.adapter.close(connection)
    return evidence


def write_contract_updates_with_progress(
    *,
    project_dir: Path,
    graph: ProjectGraph,
    result: ContractAdoptionResult,
    request: ContractCommandRequest,
    adapter: BaseAdapter,
    progress_stream: TextIO,
    use_progress_color: bool,
) -> ContractAdoptionResult:
    """Write contract declarations and report repository-update lifecycle progress."""

    from sqlbuild.compiler.contract_adoption.main.write import write_contracts

    write_progress: TransientStatusReporter = TransientStatusReporter(
        stream=progress_stream,
        use_color=use_progress_color,
    )
    write_started: float = time.monotonic()
    write_progress.start("Updating repository contracts...")
    try:
        updated_result: ContractAdoptionResult = write_contracts(
            project_dir=project_dir,
            graph=graph,
            result=result,
            overwrite=request.overwrite,
            adapter=adapter,
            cli_vars=request.cli_vars,
        )
    except Exception:
        write_progress.error(
            f"Repository contract update failed after {time.monotonic() - write_started:.2f}s"
        )
        raise
    written_count: int = len(updated_result.written_paths)
    written_label: str = "file" if written_count == 1 else "files"
    write_progress.complete(
        message=(
            f"Updated repository contracts ({written_count} {written_label}, "
            f"{time.monotonic() - write_started:.2f}s)"
        )
    )
    return updated_result
