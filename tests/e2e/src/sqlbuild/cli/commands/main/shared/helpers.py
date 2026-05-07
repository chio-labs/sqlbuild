"""Shared e2e test helpers for CLI command tests."""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path
from shutil import copytree
from typing import Any

REPO_ROOT: Path = Path(__file__).resolve().parents[8]
WAFFLE_SHOP_DIR: Path = REPO_ROOT / "tests" / "e2e" / "fixtures" / "waffle_shop"


def prepare_waffle_shop(tmp_path: Path) -> Path:
    """Copy waffle shop project to tmp dir with a fresh DuckDB target path."""

    project_dir: Path = tmp_path / "waffle_shop"
    copytree(WAFFLE_SHOP_DIR, project_dir)

    db_path: Path = project_dir / "waffle_shop.duckdb"
    if db_path.exists():
        db_path.unlink()

    return project_dir


def prepare_inline_project(
    *, tmp_path: Path, project_name: str, repo_files: Mapping[str, str]
) -> Path:
    """Write an inline-authored project to tmp dir and return its root path."""

    project_dir: Path = tmp_path / project_name
    project_dir.mkdir(parents=True, exist_ok=True)

    relative_path: str
    contents: str
    for relative_path, contents in repo_files.items():
        file_path: Path = project_dir / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(contents, encoding="utf-8")

    return project_dir


def run_sqb(
    *,
    command: tuple[str, ...],
    project_dir: Path,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run an sqb CLI command via subprocess and return the result."""

    process_env: dict[str, str] = dict(os.environ)
    if env is not None:
        process_env.update(env)

    return subprocess.run(
        ["uv", "run", "sqb", "--project-dir", str(project_dir), *command],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=process_env,
        check=False,
    )


def query_duckdb(*, db_path: Path, sql: str) -> list[tuple[Any, ...]]:
    """Open a DuckDB file and execute a query, returning all rows."""

    import duckdb

    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path), read_only=True)
    try:
        result: list[tuple[Any, ...]] = connection.execute(sql).fetchall()
    finally:
        connection.close()
    return result


def table_exists(*, db_path: Path, table_name: str, schema: str = "main") -> bool:
    """Check if a table or view exists in the DuckDB file."""

    rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=db_path,
        sql=(
            f"SELECT 1 FROM information_schema.tables "
            f"WHERE table_schema = '{schema}' AND table_name = '{table_name}'"
        ),
    )
    return len(rows) > 0


def row_count(*, db_path: Path, table_name: str, schema: str = "main") -> int:
    """Count rows in a table in the DuckDB file."""

    rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=db_path,
        sql=f"SELECT COUNT(*) FROM {schema}.{table_name}",
    )
    return int(rows[0][0])


def normalize_cli_output(output: str) -> str:
    """Normalize dynamic CLI output fragments for stable assertions."""

    normalized: str = re.sub(r"\(\d+\.\d{2}s\)", "(<time>)", output)
    normalized = re.sub(
        r"PASS=\d+  WARN=\d+  FAIL=\d+  SKIP=\d+  TOTAL=\d+  \(<time>\)",
        "PASS=<n>  WARN=<n>  FAIL=<n>  SKIP=<n>  TOTAL=<n>  (<time>)",
        normalized,
    )
    normalized = re.sub(
        r"PASS=\d+  WARN=\d+  FAIL=\d+  TOTAL=\d+",
        "PASS=<n>  WARN=<n>  FAIL=<n>  TOTAL=<n>",
        normalized,
    )
    normalized = re.sub(
        r"PASS=\d+  FAIL=\d+  TOTAL=\d+", "PASS=<n>  FAIL=<n>  TOTAL=<n>", normalized
    )
    return normalized


def assert_fragments_in_order(output: str, fragments: tuple[str, ...]) -> None:
    """Assert that fragments appear in order within normalized output."""

    normalized_output: str = normalize_cli_output(output)
    position: int = 0
    fragment: str
    for fragment in fragments:
        index: int = normalized_output.find(fragment, position)
        assert index != -1, f"missing fragment in order: {fragment!r}\n\n{normalized_output}"
        position = index + len(fragment)
