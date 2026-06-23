"""Resolve dbt profile-backed connection dictionaries."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.integrations.dbt.exceptions import DbtProfileError
from sqlbuild.integrations.dbt.helpers.profile.load import (
    default_profiles_dir,
    load_dbt_project_metadata,
    load_raw_dbt_profile,
    select_dbt_profile_output,
)
from sqlbuild.integrations.dbt.helpers.profile.normalize import normalize_dbt_profile_connection
from sqlbuild.integrations.dbt.helpers.profile.render import render_selected_dbt_profile_output
from sqlbuild.integrations.dbt.models import (
    DbtProfileConnectionRequest,
    DbtProjectProfileMetadata,
    NormalizedDbtProfileConnection,
    ResolvedDbtProfileOutput,
    SelectedDbtProfileOutput,
)
from sqlbuild.spec.models.project import DbtConfig, ProjectConfig


def resolve_dbt_profile_connection(
    *, request: DbtProfileConnectionRequest
) -> NormalizedDbtProfileConnection:
    """Resolve a dbt profile reference into SQLBuild adapter config."""

    dbt_project_dir: Path = (
        request.dbt_project_dir
        if request.dbt_project_dir is not None
        else request.sqlbuild_project_dir
    )
    profiles_dir: Path = request.profiles_dir or default_profiles_dir()
    metadata: DbtProjectProfileMetadata = load_dbt_project_metadata(project_dir=dbt_project_dir)
    profile_name: str = request.profile_name or metadata.profile_name
    selected: SelectedDbtProfileOutput = select_dbt_profile_output(
        profile=load_raw_dbt_profile(profiles_dir=profiles_dir, profile_name=profile_name),
        target_name=request.target_name,
    )
    resolved: ResolvedDbtProfileOutput = render_selected_dbt_profile_output(
        selected=selected,
        project_dir=dbt_project_dir,
        profiles_dir=profiles_dir,
        cli_vars=request.cli_vars,
    )
    return normalize_dbt_profile_connection(resolved=resolved)


def resolve_dbt_profile_raw_connection(
    *,
    raw_config: dict[str, object],
    project_dir: Path,
    adapter_name: str,
    project_config: ProjectConfig,
    cli_vars: dict[str, object] | None = None,
) -> NormalizedDbtProfileConnection | None:
    """Resolve a raw connection config if it references a dbt profile."""

    if raw_config.get("source") != "dbt_profile":
        return None
    dbt_config: DbtConfig = project_config.dbt
    dbt_project_dir: Path | None = _resolve_optional_path(
        project_root=project_dir,
        raw_value=_optional_str(raw_config.get("project_dir")) or dbt_config.project_dir,
    )
    profiles_dir: Path | None = _resolve_optional_path(
        project_root=project_dir,
        raw_value=_optional_str(raw_config.get("profiles_dir")) or dbt_config.profiles_dir,
    )
    profile_name: str | None = _optional_str(raw_config.get("profile"))
    target_name: str | None = _optional_str(raw_config.get("target")) or dbt_config.target
    resolved: NormalizedDbtProfileConnection = resolve_dbt_profile_connection(
        request=DbtProfileConnectionRequest(
            sqlbuild_project_dir=project_dir,
            dbt_project_dir=dbt_project_dir,
            profiles_dir=profiles_dir,
            profile_name=profile_name,
            target_name=target_name,
            cli_vars={} if cli_vars is None else cli_vars,
        )
    )
    if resolved.adapter != adapter_name:
        raise DbtProfileError(
            "dbt profile adapter type does not match SQLBuild project adapter: "
            f"dbt={resolved.adapter}, sqlbuild={adapter_name}"
        )
    return resolved


def _optional_str(value: object | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise DbtProfileError("dbt_profile connection values must be non-empty strings")
    return value.strip()


def _resolve_optional_path(*, project_root: Path, raw_value: str | None) -> Path | None:
    if raw_value is None:
        return None
    path: Path = Path(raw_value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (project_root.expanduser().resolve() / path).resolve()
