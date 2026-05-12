"""dbt configuration resolution helpers."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.integrations.dbt.models import DbtCliConfigOverrides, ResolvedDbtConfig
from sqlbuild.spec.models.project import DbtConfig


def resolve_dbt_config(
    *,
    project_root: Path,
    config: DbtConfig,
    overrides: DbtCliConfigOverrides,
    require_project_dir: bool,
) -> ResolvedDbtConfig:
    """Resolve dbt config from CLI overrides and project config."""

    raw_project_dir: str | None = (
        overrides.project_dir if overrides.project_dir is not None else config.project_dir
    )
    project_dir: Path | None = _resolve_optional_path(
        project_root=project_root,
        raw_value=raw_project_dir,
    )
    if require_project_dir and project_dir is None:
        raise ValueError(
            "dbt project directory is not configured\n"
            "= help: Add [dbt].project_dir to sqlbuild_project.toml or pass --project-dir "
            "to sqb dbt."
        )

    raw_profiles_dir: str | None = (
        overrides.profiles_dir if overrides.profiles_dir is not None else config.profiles_dir
    )
    profiles_dir: Path | None = _resolve_optional_path(
        project_root=project_root,
        raw_value=raw_profiles_dir,
    )
    raw_target_path: str | None = (
        overrides.target_path if overrides.target_path is not None else config.target_path
    )
    target_path: Path | None = _resolve_optional_path(
        project_root=project_root,
        raw_value=raw_target_path,
    )
    target: str | None = overrides.target if overrides.target is not None else config.target

    return ResolvedDbtConfig(
        project_dir=project_dir,
        profiles_dir=profiles_dir,
        target=target,
        target_path=target_path,
    )


def _resolve_optional_path(*, project_root: Path, raw_value: str | None) -> Path | None:
    if raw_value is None:
        return None
    resolved_project_root: Path = project_root.expanduser().resolve()
    path: Path = Path(raw_value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (resolved_project_root / path).resolve()
