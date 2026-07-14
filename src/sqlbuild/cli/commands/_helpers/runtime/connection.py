"""Connection config resolution for CLI commands."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlbuild.adapter.contract.types import BuiltinAdapter
from sqlbuild.compiler.compile.main.effective_config import build_effective_connection_config
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.integrations.dbt.exceptions import DbtProfileError
from sqlbuild.integrations.dbt.main.profile.profile_connection import (
    resolve_raw_dbt_profile_connection,
)
from sqlbuild.integrations.dbt.models import NormalizedDbtProfileConnection
from sqlbuild.spec.resolution.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)

_DUCKDB_SNOWFLAKE_LIKE_WARNING_KEYS: frozenset[str] = frozenset(
    {"account", "authenticator", "role", "token", "warehouse"}
)
_DBT_PROFILE_CONNECTION_ROUTING_KEYS: frozenset[str] = frozenset(
    {"source", "profile", "target", "project_dir", "profiles_dir"}
)
_CONNECTION_SOURCE_KEY: str = "source"
_DBT_PROFILE_CONNECTION_SOURCE: str = "dbt_profile"
_DATABASE_KEY: str = "database"
_DUCKDB_MEMORY_DATABASE: str = ":memory:"


def resolve_connection_config(
    *,
    raw_config: dict[str, object],
    project_dir: Path,
    adapter_name: str,
    discovered_inputs: DiscoveredProjectInputs | None = None,
    cli_vars: dict[str, object] | None = None,
) -> dict[str, object]:
    """Resolve relative database paths in connection config against the project directory."""

    config: dict[str, object] = dict(raw_config)
    if discovered_inputs is not None:
        resolved_dbt_profile: NormalizedDbtProfileConnection | None = (
            resolve_raw_dbt_profile_connection(
                raw_config=config,
                project_dir=project_dir,
                adapter_name=adapter_name,
                project_config=discovered_inputs.project_config,
                cli_vars=cli_vars,
            )
        )
        if resolved_dbt_profile is not None:
            for warning in resolved_dbt_profile.warnings:
                print(f"Warning: {warning}", file=sys.stderr)
            user_overrides: dict[str, object] = {
                key: value
                for key, value in raw_config.items()
                if key not in _DBT_PROFILE_CONNECTION_ROUTING_KEYS
            }
            config = {**resolved_dbt_profile.connection, **user_overrides}
    elif config.get(_CONNECTION_SOURCE_KEY) == _DBT_PROFILE_CONNECTION_SOURCE:
        raise DbtProfileError("connection.source = 'dbt_profile' requires project configuration")
    _warn_if_duckdb_has_snowflake_like_keys(adapter_name=adapter_name, config=config)
    database: object | None = config.get(_DATABASE_KEY)
    if (
        adapter_name == BuiltinAdapter.DUCKDB
        and isinstance(database, str)
        and not Path(database).is_absolute()
        and database != _DUCKDB_MEMORY_DATABASE
    ):
        config[_DATABASE_KEY] = str(project_dir / database)
    return config


def _warn_if_duckdb_has_snowflake_like_keys(
    *, adapter_name: str, config: dict[str, object]
) -> None:
    if adapter_name != BuiltinAdapter.DUCKDB:
        return
    suspicious_keys: tuple[str, ...] = tuple(
        sorted(key for key in config if key in _DUCKDB_SNOWFLAKE_LIKE_WARNING_KEYS)
    )
    if not suspicious_keys:
        return
    key_list: str = ", ".join(suspicious_keys)
    print(
        "Warning: DuckDB adapter is active, but connection contains "
        f"Snowflake-like keys: {key_list}. If this is a Snowflake local config, "
        "add top-level `adapter: snowflake` to sqlbuild_local.toml.",
        file=sys.stderr,
    )


def resolve_project_connection_config(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    project_dir: Path,
    selected_target: str | None = None,
    cli_vars: dict[str, object] | None = None,
) -> dict[str, object]:
    """Resolve the effective project connection config for CLI command execution."""

    return resolve_connection_config(
        raw_config=build_effective_connection_config(
            discovered_inputs=discovered_inputs,
            selected_target=selected_target,
            cli_vars=cli_vars,
        ),
        project_dir=project_dir,
        adapter_name=resolve_effective_adapter_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        ),
        discovered_inputs=discovered_inputs,
        cli_vars=cli_vars,
    )


def resolve_target_connection_config(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    project_dir: Path,
    target_name: str,
    cli_vars: dict[str, object] | None = None,
) -> dict[str, object]:
    """Resolve the effective connection config for one named target."""

    return resolve_connection_config(
        raw_config=build_effective_connection_config(
            discovered_inputs=discovered_inputs,
            selected_target=target_name,
            cli_vars=cli_vars,
        ),
        project_dir=project_dir,
        adapter_name=resolve_effective_adapter_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        ),
        discovered_inputs=discovered_inputs,
        cli_vars=cli_vars,
    )
