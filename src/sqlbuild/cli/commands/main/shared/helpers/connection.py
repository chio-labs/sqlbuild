"""Connection config resolution for CLI commands."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.adapter.shared.types import BuiltinAdapter
from sqlbuild.compiler.compile.main.effective_config import build_effective_connection_config
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs


def resolve_connection_config(
    *,
    raw_config: dict[str, object],
    project_dir: Path,
    adapter_name: str,
) -> dict[str, object]:
    """Resolve relative database paths in connection config against the project directory."""

    config: dict[str, object] = dict(raw_config)
    database: object | None = config.get("database")
    if (
        adapter_name == BuiltinAdapter.DUCKDB
        and isinstance(database, str)
        and not Path(database).is_absolute()
        and database != ":memory:"
    ):
        config["database"] = str(project_dir / database)
    return config


def resolve_project_connection_config(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    project_dir: Path,
) -> dict[str, object]:
    """Resolve the effective project connection config for CLI command execution."""

    return resolve_connection_config(
        raw_config=build_effective_connection_config(discovered_inputs=discovered_inputs),
        project_dir=project_dir,
        adapter_name=discovered_inputs.project_config.adapter,
    )
