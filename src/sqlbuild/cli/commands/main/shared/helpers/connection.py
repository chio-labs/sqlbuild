"""Connection config resolution for CLI commands."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlbuild.adapter.shared.types import BuiltinAdapter
from sqlbuild.compiler.compile.main.effective_config import build_effective_connection_config
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.models.project import resolve_effective_adapter_name

_DUCKDB_SNOWFLAKE_LIKE_WARNING_KEYS: frozenset[str] = frozenset(
    {"account", "authenticator", "role", "token", "warehouse"}
)


def resolve_connection_config(
    *,
    raw_config: dict[str, object],
    project_dir: Path,
    adapter_name: str,
) -> dict[str, object]:
    """Resolve relative database paths in connection config against the project directory."""

    config: dict[str, object] = dict(raw_config)
    _warn_if_duckdb_has_snowflake_like_keys(adapter_name=adapter_name, config=config)
    database: object | None = config.get("database")
    if (
        adapter_name == BuiltinAdapter.DUCKDB
        and isinstance(database, str)
        and not Path(database).is_absolute()
        and database != ":memory:"
    ):
        config["database"] = str(project_dir / database)
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
        "add top-level `adapter: snowflake` to sqlbuild_local.yml.",
        file=sys.stderr,
    )


def resolve_project_connection_config(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    project_dir: Path,
) -> dict[str, object]:
    """Resolve the effective project connection config for CLI command execution."""

    return resolve_connection_config(
        raw_config=build_effective_connection_config(discovered_inputs=discovered_inputs),
        project_dir=project_dir,
        adapter_name=resolve_effective_adapter_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        ),
    )


def resolve_environment_connection_config(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    project_dir: Path,
    environment_name: str,
) -> dict[str, object]:
    """Resolve the effective connection config for one named environment."""

    return resolve_connection_config(
        raw_config=build_effective_connection_config(
            discovered_inputs=discovered_inputs,
            selected_environment=environment_name,
        ),
        project_dir=project_dir,
        adapter_name=resolve_effective_adapter_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        ),
    )
