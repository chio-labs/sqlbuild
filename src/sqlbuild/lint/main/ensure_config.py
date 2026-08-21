"""Public entry point for scaffolding the project sqruff config."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.lint._helpers.sqruff_scaffold import ensure_sqruff_config as _ensure_sqruff_config


def ensure_sqruff_config(
    *, project_dir: Path, config_path: str, sqruff_enabled: bool
) -> str | None:
    """Create the sqruff config when missing and return any dialect drift warning."""

    return _ensure_sqruff_config(
        project_dir=project_dir, config_path=config_path, sqruff_enabled=sqruff_enabled
    )
