"""Effective target and compile-cache resolution helpers."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile._helpers.attachment.core import build_effective_vars
from sqlbuild.compiler.compile._helpers.render.context_templates import (
    resolve_early_model_templates,
    resolve_run_id,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.fact_cache.main._compile_cache_root import compile_cache_root
from sqlbuild.spec.contracts.main.resolve_target_config import resolve_target_config
from sqlbuild.spec.contracts.main.resolve_target_name import resolve_target_name
from sqlbuild.spec.contracts.models import TargetConfig


def build_compile_target_context(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    selected_target: str | None,
    no_cache: bool,
) -> tuple[str | None, TargetConfig | None, Path | None]:
    """Resolve the effective target and shared project-local compile-cache directory."""

    target_name: str | None = resolve_target_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_target=selected_target,
    )
    target_config: TargetConfig | None = (
        resolve_target_config(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
            target_name=target_name,
        )
        if target_name is not None
        else None
    )
    cache_dir: Path | None = compile_cache_root(
        project_dir=discovered_inputs.project_dir,
        target_config=target_config,
        no_cache=no_cache,
    )
    return target_name, target_config, cache_dir


def build_effective_target_namespace(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    selected_target: str | None,
    connection_database: object | None,
    connection_schema: object | None,
    default_database: str | None,
    default_schema: str | None,
) -> tuple[str | None, TargetConfig | None, str | None, str | None]:
    """Resolve the target and its effective database/schema without compiling resources."""

    target_name: str | None = resolve_target_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_target=selected_target,
    )
    target_config: TargetConfig | None = (
        resolve_target_config(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
            target_name=target_name,
        )
        if target_name is not None
        else None
    )
    effective_vars: dict[str, object] = build_effective_vars(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        target_config=target_config,
        cli_vars={},
    )
    target_values: dict[str, object] = resolve_early_model_templates(
        values={
            "database": (target_config.database if target_config is not None else None)
            or connection_database
            or default_database,
            "schema": (target_config.schema if target_config is not None else None)
            or connection_schema
            or default_schema,
        },
        effective_vars=effective_vars,
        effective_target_name=target_name,
        run_id=resolve_run_id(selected_run_id=None),
    )
    return (
        target_name,
        target_config,
        _optional_string(target_values.get("database")),
        _optional_string(target_values.get("schema")),
    )


def _optional_string(value: object | None) -> str | None:
    return value if isinstance(value, str) and value else None
