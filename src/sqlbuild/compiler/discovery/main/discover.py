"""Discovery entrypoints."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.main.compile_cache_root import compile_cache_root
from sqlbuild.compiler.discovery._helpers.filesystem.aggregation import (
    build_discovered_project_inputs,
)
from sqlbuild.compiler.discovery._helpers.filesystem.python_paths import (
    validate_project_python_paths,
)
from sqlbuild.compiler.discovery._helpers.validation.discovery import validate_discovered_inputs
from sqlbuild.compiler.discovery._helpers.yml.project import (
    load_local_config,
    load_project_config,
)
from sqlbuild.compiler.discovery.constants import (
    DISCOVERY_FACT_CACHE_ALGORITHM,
    DISCOVERY_FACT_CACHE_NAMESPACE,
    SQL_ANALYSIS_SETTING_KEY,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs, DiscoveryCacheRequest
from sqlbuild.compiler.fact_cache.classes.fact_cache_store import FactCacheStore
from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle
from sqlbuild.spec.contracts.exceptions import SpecConfigError
from sqlbuild.spec.contracts.main.resolve_target_config import resolve_target_config
from sqlbuild.spec.contracts.main.resolve_target_name import resolve_target_name
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig, TargetConfig


def discover_project_inputs(
    *,
    project_dir: Path,
    sql_analysis_enabled_override: bool | None = None,
    extract_output_column_locations: bool = True,
    cache_request: DiscoveryCacheRequest | None = None,
) -> DiscoveredProjectInputs:
    """Load all raw project inputs from disk before semantic resolution."""

    with OperationLifecycle(operation_kind="project", operation_name="project_discovery"):
        return _discover_project_inputs(
            project_dir=project_dir,
            sql_analysis_enabled_override=sql_analysis_enabled_override,
            extract_output_column_locations=extract_output_column_locations,
            cache_request=cache_request,
        )


def _discover_project_inputs(
    *,
    project_dir: Path,
    sql_analysis_enabled_override: bool | None,
    extract_output_column_locations: bool,
    cache_request: DiscoveryCacheRequest | None,
) -> DiscoveredProjectInputs:
    with OperationLifecycle(operation_kind="project", operation_name="discovery_project_assembly"):
        return _assemble_discovered_project_inputs(
            project_dir=project_dir,
            sql_analysis_enabled_override=sql_analysis_enabled_override,
            extract_output_column_locations=extract_output_column_locations,
            cache_request=cache_request,
        )


def _assemble_discovered_project_inputs(
    *,
    project_dir: Path,
    sql_analysis_enabled_override: bool | None,
    extract_output_column_locations: bool,
    cache_request: DiscoveryCacheRequest | None,
) -> DiscoveredProjectInputs:
    project_config: ProjectConfig = load_project_config(project_dir=project_dir)
    local_config: LocalConfig = load_local_config(project_dir=project_dir)
    validate_project_python_paths(project_dir=project_dir)
    sql_analysis_enabled: bool = (
        sql_analysis_enabled_override
        if sql_analysis_enabled_override is not None
        else (
            local_config.settings.sql_analysis
            if SQL_ANALYSIS_SETTING_KEY in local_config.setting_overrides
            else project_config.settings.sql_analysis
        )
    )
    with FactCacheStore(
        root=_discovery_cache_root(
            project_dir=project_dir,
            project_config=project_config,
            local_config=local_config,
            cache_request=cache_request,
        ),
        namespace=DISCOVERY_FACT_CACHE_NAMESPACE,
        algorithm=DISCOVERY_FACT_CACHE_ALGORITHM,
    ) as fact_cache:
        discovered_inputs: DiscoveredProjectInputs = build_discovered_project_inputs(
            project_dir=project_dir,
            project_config=project_config,
            local_config=local_config,
            sql_analysis_enabled=sql_analysis_enabled,
            extract_output_column_locations=extract_output_column_locations,
            fact_cache=fact_cache,
        )
    validate_discovered_inputs(discovered_inputs)
    from sqlbuild.runtime.event_exporting.main.configure_discovered_event_exporters import (
        configure_discovered_event_exporters,
    )

    _ = configure_discovered_event_exporters(discovered_inputs)
    return discovered_inputs


def _discovery_cache_root(
    *,
    project_dir: Path,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    cache_request: DiscoveryCacheRequest | None,
) -> Path | None:
    if cache_request is None or cache_request.no_cache:
        return None
    try:
        target_name: str | None = resolve_target_name(
            project_config=project_config,
            local_config=local_config,
            selected_target=cache_request.selected_target,
        )
        target_config: TargetConfig | None = (
            resolve_target_config(
                project_config=project_config,
                local_config=local_config,
                target_name=target_name,
            )
            if target_name is not None
            else None
        )
    except SpecConfigError:
        return None
    return compile_cache_root(
        project_dir=project_dir, target_config=target_config, no_cache=cache_request.no_cache
    )
