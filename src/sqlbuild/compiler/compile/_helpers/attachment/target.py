"""Effective target and compile-cache resolution helpers."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from sqlbuild.compiler.compile._helpers.attachment.core import build_effective_vars
from sqlbuild.compiler.compile._helpers.render.context_templates import (
    resolve_early_model_templates,
    resolve_run_id,
)
from sqlbuild.compiler.compile.constants import (
    COMPILE_CACHE_DISABLE_ENV_VAR,
    COMPILE_CACHE_DISABLE_VALUE,
    RETIRED_FACT_CACHE_DIRECTORY_NAME,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.frontier.constants import (
    COMPILER_CACHE_DIRECTORY_NAME,
    RETIRED_CACHE_NAMESPACE_SUFFIXES,
)
from sqlbuild.compiler.frontier.main.compiler_cache_directory import compiler_cache_directory
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


def compile_cache_root(
    *, project_dir: Path | None, target_config: TargetConfig | None, no_cache: bool
) -> Path | None:
    """Return the shared compile-cache directory, or None when caching is disabled."""

    if (
        no_cache
        or project_dir is None
        or (target_config is not None and target_config.compile_cache is False)
        or os.environ.get(COMPILE_CACHE_DISABLE_ENV_VAR) == COMPILE_CACHE_DISABLE_VALUE
    ):
        return None
    root: Path = compiler_cache_directory(project_dir)
    _remove_retired_fact_caches(root=root)
    return root


def _remove_retired_fact_caches(*, root: Path) -> None:
    """Delete the per-file fact caches older releases kept under every engine's compiler root."""

    for suffix in RETIRED_CACHE_NAMESPACE_SUFFIXES:
        retired: Path = (
            root.parent
            / f"{COMPILER_CACHE_DIRECTORY_NAME}{suffix}"
            / (RETIRED_FACT_CACHE_DIRECTORY_NAME)
        )
        if retired.is_dir():
            shutil.rmtree(retired, ignore_errors=True)


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
