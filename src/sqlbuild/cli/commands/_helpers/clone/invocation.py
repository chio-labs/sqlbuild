"""Clone command invocation resolution phase."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.clone.models import CloneCommandRequest, CloneInvocation
from sqlbuild.cli.commands._helpers.clone.validation import validate_clone_request
from sqlbuild.cli.commands._helpers.runtime.adapters import resolve_adapter
from sqlbuild.cli.progress.classes.planning_progress_reporter import PlanningProgressReporter
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.presentation.main.supports_color import supports_color
from sqlbuild.spec.resolution.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)


def resolve_clone_invocation(*, request: CloneCommandRequest) -> CloneInvocation:
    """Resolve discovery, adapter, and output context for clone."""

    effective_project_dir: Path = (
        request.project_dir if request.project_dir is not None else Path.cwd()
    )
    use_color: bool = not request.no_color and supports_color()
    progress_stream: TextIO = sys.stdout
    progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=progress_stream,
        use_color=use_color,
    )
    progress.start("Discovering project...")
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    progress.complete("Discovered project.")
    validate_clone_request(
        discovered_inputs=discovered_inputs,
        origin_target_name=request.origin_target_name,
        destination_target_name=request.destination_target_name,
    )
    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(
        adapter_name=adapter_name, project_dir=effective_project_dir
    )
    return CloneInvocation(
        effective_project_dir=effective_project_dir,
        discovered_inputs=discovered_inputs,
        adapter_name=adapter_name,
        adapter=adapter,
        use_color=use_color,
        progress_stream=progress_stream,
    )
