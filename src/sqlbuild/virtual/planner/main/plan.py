"""Virtual-mode planning entrypoint."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.runtime.contracts.models import ConnectionHooks
from sqlbuild.virtual.executor.main._resolve_plan import resolve_virtual_plan
from sqlbuild.virtual.planner.models import VirtualPlanOptions


def run_virtual_plan_pipeline(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    connection_config: dict[str, object] | None = None,
    options: VirtualPlanOptions | None = None,
    hooks: ConnectionHooks | None = None,
) -> CompilePipelineResult:
    """Run the read-only build-grade virtual planning pipeline."""

    if connection_config is None:
        raise PlannerInputError("virtual planning requires explicit connection_config")
    return resolve_virtual_plan(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        connection_config=connection_config,
        options=options if options is not None else VirtualPlanOptions(),
        hooks=hooks if hooks is not None else ConnectionHooks(),
    )
