"""The Recall views section of the investigation guide, rendered by `sqb recall schema` itself."""

import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts.docs_skill.constants import SCHEMA_SECTION_END, SCHEMA_SECTION_START

_PROJECT_TOML: str = 'name = "orders_shop"\nadapter = "duckdb"\n'
_TABLE_MARKER: str = " (table)"


def _sqb(project_dir: Path, *args: str) -> str:
    home: Path = project_dir / "home"
    completed: subprocess.CompletedProcess[str] = subprocess.run(
        [str(Path(sys.executable).with_name("sqlbuild-python")), *args],
        cwd=project_dir,
        capture_output=True,
        check=True,
        text=True,
        env={
            **os.environ,
            "HOME": str(home),
            "XDG_CACHE_HOME": str(home / ".cache"),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "NO_COLOR": "1",
        },
    )
    return completed.stdout


def render_recall_views() -> str:
    """Every Recall view, its columns and join keys, as `sqb recall schema` prints a new store."""

    with tempfile.TemporaryDirectory() as directory:
        project_dir: Path = Path(directory)
        (project_dir / "sqlbuild_project.toml").write_text(_PROJECT_TOML, encoding="utf-8")
        script: str = _sqb(project_dir, "recall", "schema", "--ddl")
        (project_dir / "logs").mkdir()
        with sqlite3.connect(project_dir / "logs" / "recall.sqlite3") as connection:
            connection.executescript(script)
        connection.close()
        described: list[str] = _sqb(project_dir, "recall", "schema").splitlines()
    views: list[str] = []
    for line in described[1:]:
        if _TABLE_MARKER in line and not line.startswith(" "):
            break
        views.append(line)
    return "\n".join(views).strip() + "\n"


def with_recall_views(guide: str, views: str) -> str:
    """`guide` with its generated schema section replaced by `views`."""

    start: int = guide.index(SCHEMA_SECTION_START) + len(SCHEMA_SECTION_START)
    end: int = guide.index(SCHEMA_SECTION_END)
    return f"{guide[:start]}\n\n```text\n{views}```\n\n{guide[end:]}"
