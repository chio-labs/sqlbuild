"""dbt profile connection entrypoint."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.integrations.dbt.helpers.profile.connection import resolve_dbt_profile_raw_connection
from sqlbuild.integrations.dbt.models import NormalizedDbtProfileConnection
from sqlbuild.spec.models.project import ProjectConfig


def resolve_raw_dbt_profile_connection(
    *,
    raw_config: dict[str, object],
    project_dir: Path,
    adapter_name: str,
    project_config: ProjectConfig,
    cli_vars: dict[str, object] | None = None,
) -> NormalizedDbtProfileConnection | None:
    """Resolve a raw connection config if it references a dbt profile."""

    return resolve_dbt_profile_raw_connection(
        raw_config=raw_config,
        project_dir=project_dir,
        adapter_name=adapter_name,
        project_config=project_config,
        cli_vars=cli_vars,
    )
