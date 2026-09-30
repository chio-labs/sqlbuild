"""Compile-cache root resolution for discovery facts."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery.models import DiscoveryCacheRequest
from sqlbuild.compiler.fact_cache.main._compile_cache_root import compile_cache_root
from sqlbuild.spec.contracts.exceptions import SpecConfigError
from sqlbuild.spec.contracts.main.resolve_target_config import resolve_target_config
from sqlbuild.spec.contracts.main.resolve_target_name import resolve_target_name
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig, TargetConfig


def discovery_cache_root(
    *,
    project_dir: Path,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    cache_request: DiscoveryCacheRequest | None,
) -> Path | None:
    """Return the compile-cache root for discovery facts, or None when caching is off."""

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
