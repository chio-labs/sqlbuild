"""Public entrypoint for pre-connection external source-load execution."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.build._helpers.external_source_loads import (
    run_external_source_loads_before_connections as _run_external_source_loads_before_connections,
)
from sqlbuild.executor.build.models import (
    BuildCallbacks,
    BuildRuntimeParams,
    ExternalSourceLoadResults,
)


def run_external_source_loads_before_connections(
    *,
    plan: PlanOutput,
    loader_functions: tuple[DiscoveredLoaderFunction, ...],
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    runtime: BuildRuntimeParams,
    callbacks: BuildCallbacks,
    precompleted_keys: frozenset[CompiledObjectKey] = frozenset(),
) -> ExternalSourceLoadResults:
    """Run external source-load nodes before SQLBuild opens warehouse connections."""

    return _run_external_source_loads_before_connections(
        plan=plan,
        loader_functions=loader_functions,
        adapter=adapter,
        connection_config=connection_config,
        runtime=runtime,
        callbacks=callbacks,
        precompleted_keys=precompleted_keys,
    )
