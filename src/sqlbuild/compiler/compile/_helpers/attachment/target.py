"""Effective target and compile-cache resolution helpers."""

from __future__ import annotations

import os
from pathlib import Path

from sqlbuild.compiler.compile.constants import (
    COMPILE_CACHE_DISABLE_ENV_VAR,
    COMPILE_CACHE_DISABLE_VALUE,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
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
    cache_disabled: bool = (
        no_cache
        or (target_config is not None and target_config.compile_cache is False)
        or os.environ.get(COMPILE_CACHE_DISABLE_ENV_VAR) == COMPILE_CACHE_DISABLE_VALUE
    )
    project_dir: Path | None = discovered_inputs.project_dir
    cache_dir: Path | None = (
        None if cache_disabled or project_dir is None else project_dir / "target" / "compile-cache"
    )
    return target_name, target_config, cache_dir
