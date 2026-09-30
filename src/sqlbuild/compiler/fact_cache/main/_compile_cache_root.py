"""Project-local compile-cache root resolution."""

from __future__ import annotations

import os
from pathlib import Path

from sqlbuild.compiler.compile.constants import (
    COMPILE_CACHE_DISABLE_ENV_VAR,
    COMPILE_CACHE_DISABLE_VALUE,
)
from sqlbuild.spec.contracts.models import TargetConfig


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
    return project_dir / "target" / "cache" / "compiler"
