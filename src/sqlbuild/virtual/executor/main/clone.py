"""Virtual clone public entrypoint."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.models import ClonePipelineConnection, ClonePipelineResult
from sqlbuild.virtual.executor._helpers.clone import (
    build_clone_origin_lookup,
    build_clone_project_context,
    compile_clone_pipeline,
    hydrate_clone_model_relations,
    hydrate_clone_seed_relations,
    resolve_clone_versions,
)
from sqlbuild.virtual.executor.models import (
    CloneOptions,
    CloneOriginLookup,
    CloneProjectContext,
    CloneVersions,
    VirtualCloneItemResult,
    VirtualCloneResult,
)
from sqlbuild.virtual.state.main.environments.runtime import build_state_runtime


def run_virtual_clone(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    origin_target_name: str,
    destination_target_name: str,
    destination_connection_config: dict[str, object],
    options: CloneOptions | None = None,
) -> VirtualCloneResult:
    """Hydrate target physical versions from matching source warehouse artifacts."""

    resolved_options: CloneOptions = options if options is not None else CloneOptions()
    destination_connection: Any = adapter.connect(destination_connection_config)
    try:
        config, backend = build_state_runtime(
            discovered_inputs=discovered_inputs,
            project_dir=project_dir,
            selected_target=destination_target_name,
        )
        state_connection: Any = backend.connect(config.connection)
        try:
            clone_pipeline: ClonePipelineResult = compile_clone_pipeline(
                discovered_inputs=discovered_inputs,
                adapter=adapter,
                origin_target_name=origin_target_name,
                destination_target_name=destination_target_name,
                destination_connection=ClonePipelineConnection(
                    config=destination_connection_config,
                    handle=destination_connection,
                ),
                no_sql_validation=resolved_options.no_sql_validation,
                select=resolved_options.select,
                exclude=resolved_options.exclude,
                cli_vars=resolved_options.cli_vars,
                external_sql_reference_resolver=resolved_options.external_sql_reference_resolver,
            )
            context: CloneProjectContext = build_clone_project_context(clone_pipeline)
            versions: CloneVersions = resolve_clone_versions(
                backend=backend,
                state_connection=state_connection,
                schema=config.schema,
                clone_pipeline=clone_pipeline,
                context=context,
                virtual_environment_name=resolved_options.virtual_environment_name,
                discovered_inputs=discovered_inputs,
                project_dir=project_dir,
                origin_target_name=origin_target_name,
            )
            origin_lookup: CloneOriginLookup = build_clone_origin_lookup(
                adapter=adapter,
                destination_connection=destination_connection,
                context=context,
                versions=versions,
            )
            model_items: tuple[VirtualCloneItemResult, ...] = hydrate_clone_model_relations(
                backend=backend,
                adapter=adapter,
                destination_connection=destination_connection,
                config_schema=config.schema,
                config_connection=config.connection,
                context=context,
                versions=versions,
                origin_lookup=origin_lookup,
                skip_locked=resolved_options.skip_locked,
            )
            seed_items: tuple[VirtualCloneItemResult, ...] = hydrate_clone_seed_relations(
                backend=backend,
                adapter=adapter,
                destination_connection=destination_connection,
                config_schema=config.schema,
                config_connection=config.connection,
                context=context,
                versions=versions,
                origin_lookup=origin_lookup,
            )
        finally:
            backend.close(state_connection)
    finally:
        adapter.close(destination_connection)
    return VirtualCloneResult(
        mode=versions.mode,
        origin_environment=origin_target_name,
        destination_environment=destination_target_name,
        destination_virtual_environment=resolved_options.virtual_environment_name,
        origin_state_used=versions.origin_state_used,
        item_results=(*model_items, *seed_items),
    )
