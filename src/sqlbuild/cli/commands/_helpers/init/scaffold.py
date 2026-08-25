"""Project scaffolding helpers for sqb init."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.lint.constants import DEFAULT_SQRUFF_CONFIG_CONTENT


def scaffold_blank_project(*, base_dir: Path, project_name: str) -> None:
    """Create the default blank SQLBuild project structure."""

    directories: tuple[str, ...] = (
        "models/staging",
        "models/marts",
        "schemas",
        "sources",
        "seeds",
        "loaders",
        "tasks",
        "assets",
        "checks",
        "hooks/sql",
        "hooks/python",
        "tests/unit",
        "tests/scenarios",
        "functions/sql",
        "functions/python",
        "macros",
        "audits",
    )
    for directory in directories:
        (base_dir / directory).mkdir(parents=True, exist_ok=True)

    (base_dir / "sqlbuild_project.toml").write_text(_build_project_toml(project_name=project_name))

    sqruff_config: Path = base_dir / ".sqruff"
    if not sqruff_config.exists():
        sqruff_config.write_text(DEFAULT_SQRUFF_CONFIG_CONTENT)

    for directory in directories:
        gitkeep: Path = base_dir / directory / ".gitkeep"
        if not any((base_dir / directory).iterdir()):
            gitkeep.touch()


def _build_project_toml(*, project_name: str) -> str:
    return f'''name = "{project_name}"
adapter = "duckdb"
default_target = "dev"

[connection]
database = "{project_name}.duckdb"

[settings]
default_audit_severity = "warn"

[defaults]
materialized = "table"

[targets.prod]
schema = "prod"

[targets.dev]
schema = "dev"
'''
