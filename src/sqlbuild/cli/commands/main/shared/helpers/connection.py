"""Connection config resolution for CLI commands."""

from __future__ import annotations

from pathlib import Path


def resolve_connection_config(
    *,
    raw_config: dict[str, object],
    project_dir: Path,
) -> dict[str, object]:
    """Resolve relative database paths in connection config against the project directory."""

    config: dict[str, object] = dict(raw_config)
    database: object | None = config.get("database")
    if isinstance(database, str) and not Path(database).is_absolute() and database != ":memory:":
        config["database"] = str(project_dir / database)
    return config
