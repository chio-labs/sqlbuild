from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import quote

from sqlbuild.integrations.postgres.client import PostgresAdapter

REPO_ROOT: Path = Path(__file__).resolve().parents[6]


def run_sqb_with_ingestr(*, command: tuple[str, ...], project_dir: Path) -> subprocess.CompletedProcess[str]:
    process_env: dict[str, str] = dict(os.environ)
    return subprocess.run(
        [
            "uv",
            "run",
            "--with",
            "ingestr",
            "sqb",
            "--project-dir",
            str(project_dir),
            *command,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=process_env,
        check=False,
    )


def postgres_uri(config: Mapping[str, object]) -> str:
    user: str = quote(str(config["user"]))
    password: str = quote(str(config["password"]))
    host: str = str(config["host"])
    port: object = config["port"]
    database: str = quote(str(config["dbname"]))
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


def postgres_project_toml(*, project_name: str, config: Mapping[str, object]) -> str:
    return f"""
name = "{project_name}"
adapter = "postgres"

[connection]
host = "{config["host"]}"
port = {config["port"]}
dbname = "{config["dbname"]}"
user = "{config["user"]}"
password = "{config["password"]}"
""".strip() + "\n"


def duckdb_project_toml(*, project_name: str, database_path: Path) -> str:
    return f"""
name = "{project_name}"
adapter = "duckdb"

[connection]
database = "{database_path}"
""".strip() + "\n"


def execute_postgres_sql(*, config: Mapping[str, object], sql: str) -> None:
    adapter: PostgresAdapter = PostgresAdapter()
    connection: Any = adapter.connect(dict(config))
    try:
        adapter.execute(connection, sql)
    finally:
        adapter.close(connection)


def fetch_postgres_rows(*, config: Mapping[str, object], sql: str) -> tuple[tuple[object, ...], ...]:
    adapter: PostgresAdapter = PostgresAdapter()
    connection: Any = adapter.connect(dict(config))
    try:
        cursor: Any = adapter.execute(connection, sql)
        return tuple(cursor.fetchall())
    finally:
        adapter.close(connection)


def fetch_duckdb_rows(*, database_path: Path, sql: str) -> tuple[tuple[object, ...], ...]:
    import duckdb

    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(database_path), read_only=True)
    try:
        return tuple(connection.execute(sql).fetchall())
    finally:
        connection.close()


def write_project_files(*, project_dir: Path, files: Mapping[str, str]) -> None:
    relative_path: str
    contents: str
    for relative_path, contents in files.items():
        file_path: Path = project_dir / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(contents, encoding="utf-8")
