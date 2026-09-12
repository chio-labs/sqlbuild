"""Disposable SQLite cache for relation-level project lineage."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
from contextlib import closing
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from sqlbuild.cli.commands.constants import TARGET_DIRECTORY_NAME
from sqlbuild.cli.commands.models import LineageNode, RelationLineageIndex
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.pipeline.models import ProjectGraph

_CACHE_SCHEMA_VERSION: int = 1
_CACHE_ALGORITHM_VERSION: str = "relation-lineage-graph-v4"
_CACHE_RELATIVE_PATH: Path = Path("cache/lineage/v1/structural-graph.sqlite3")
_CACHE_MAX_BYTES: int = 50_000_000
_CACHE_MAX_ROWS: int = 1_000_000
_SQLITE_TIMEOUT_SECONDS: float = 5.0
_FINGERPRINT_SUFFIXES: frozenset[str] = frozenset({".csv", ".py", ".sql", ".toml", ".yaml", ".yml"})
_FINGERPRINT_ROOT_FILES: frozenset[str] = frozenset({".gitignore", ".sqlbuildignore"})
_EXCLUDED_ROOTS: frozenset[str] = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "node_modules",
        "target",
        "venv",
    }
)
_EXCLUDED_PATH_PARTS: frozenset[str] = frozenset({"__pycache__"})
_ENVIRONMENT_PATTERN: re.Pattern[bytes] = re.compile(rb"ENV:\s*([A-Za-z0-9_]+)")
_ENVIRONMENT_MARKER: bytes = b"ENV:"
_DYNAMIC_CONTEXT_MARKER: bytes = b"CTX:"
_DYNAMIC_CONTEXT_GRAPH_SUFFIXES: frozenset[str] = frozenset({".py", ".toml"})
_NON_ASCII_BYTE_START: int = 128


def relation_lineage_fingerprint(
    *, project_dir: Path, cli_vars: dict[str, object] | None
) -> str | None:
    """Hash authored project inputs and invocation context without retaining their values."""

    try:
        digest: Any = hashlib.sha256()
        digest.update(_CACHE_ALGORITHM_VERSION.encode("ascii"))
        digest.update(_sqlbuild_version().encode("utf-8"))
        digest.update(
            json.dumps(
                {} if cli_vars is None else cli_vars,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("ascii")
        )
        environment_names: set[str] = set()
        for path in _authored_files(project_dir=project_dir):
            relative_path: str = path.relative_to(project_dir).as_posix()
            contents: bytes = path.read_bytes()
            if (
                _DYNAMIC_CONTEXT_MARKER in contents
                and path.suffix.lower() in _DYNAMIC_CONTEXT_GRAPH_SUFFIXES
            ):
                return None
            environment_matches: list[re.Match[bytes]] = list(
                _ENVIRONMENT_PATTERN.finditer(contents)
            )
            if contents.count(_ENVIRONMENT_MARKER) != len(environment_matches):
                return None
            if any(
                match.end() < len(contents) and contents[match.end()] >= _NON_ASCII_BYTE_START
                for match in environment_matches
            ):
                return None
            environment_names.update(
                match.group(1).decode("ascii") for match in environment_matches
            )
            digest.update(len(relative_path).to_bytes(8, byteorder="big"))
            digest.update(relative_path.encode("utf-8"))
            digest.update(len(contents).to_bytes(8, byteorder="big"))
            digest.update(contents)
        for name in sorted(environment_names):
            digest.update(name.encode("ascii"))
            digest.update(os.environ.get(name, "<missing>").encode("utf-8"))
        return digest.hexdigest()
    except (OSError, TypeError, UnicodeError, ValueError):
        return None


def read_relation_lineage_cache(
    *, project_dir: Path, fingerprint: str
) -> RelationLineageIndex | None:
    """Read a verified structural graph, treating every fault as a cache miss."""

    database_path: Path = _cache_path(project_dir=project_dir)
    try:
        if database_path.stat().st_size > _CACHE_MAX_BYTES:
            return None
        with closing(
            sqlite3.connect(
                f"file:{database_path}?mode=ro",
                uri=True,
                timeout=_SQLITE_TIMEOUT_SECONDS,
            )
        ) as connection:
            metadata: dict[str, str] = dict(connection.execute("SELECT key, value FROM metadata"))
            if metadata != {
                "algorithm_version": _CACHE_ALGORITHM_VERSION,
                "input_fingerprint": fingerprint,
                "schema_version": str(_CACHE_SCHEMA_VERSION),
            }:
                return None
            return _read_index(connection=connection)
    except (KeyError, OSError, sqlite3.DatabaseError, TypeError, ValueError):
        return None


def write_relation_lineage_cache(
    *, project_dir: Path, fingerprint: str, graph: ProjectGraph
) -> RelationLineageIndex:
    """Build the structural projection and atomically publish its SQLite cache."""

    index: RelationLineageIndex = _relation_index(graph=graph)
    directory: Path = _cache_path(project_dir=project_dir).parent
    temporary_path: Path | None = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=".structural-graph-", dir=directory)
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        with closing(
            sqlite3.connect(temporary_path, timeout=_SQLITE_TIMEOUT_SECONDS)
        ) as connection:
            _create_schema(connection=connection)
            _write_index(connection=connection, fingerprint=fingerprint, index=index)
            connection.commit()
        temporary_path.replace(_cache_path(project_dir=project_dir))
    except (OSError, sqlite3.DatabaseError, TypeError, ValueError):
        pass
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return index


def _authored_files(*, project_dir: Path) -> tuple[Path, ...]:
    return tuple(
        sorted(
            path
            for path in project_dir.rglob("*")
            if path.is_file()
            and not _is_excluded(path=path, project_dir=project_dir)
            and (
                path.suffix.lower() in _FINGERPRINT_SUFFIXES or path.name in _FINGERPRINT_ROOT_FILES
            )
        )
    )


def _is_excluded(*, path: Path, project_dir: Path) -> bool:
    parts: tuple[str, ...] = path.relative_to(project_dir).parts
    return (
        not parts or parts[0] in _EXCLUDED_ROOTS or bool(_EXCLUDED_PATH_PARTS.intersection(parts))
    )


def _cache_path(*, project_dir: Path) -> Path:
    return project_dir / TARGET_DIRECTORY_NAME / _CACHE_RELATIVE_PATH


def _relation_index(*, graph: ProjectGraph) -> RelationLineageIndex:
    keys: frozenset[CompiledObjectKey] = frozenset(graph.all_keys.values())
    return RelationLineageIndex(
        nodes={key: _lineage_node(project=graph.project, key=key) for key in keys},
        upstream_deps=graph.upstream_deps,
        downstream_deps=graph.downstream_deps,
        tag_index=graph.tag_index,
        path_index=graph.path_index,
        all_keys=graph.all_keys,
    )


def _lineage_node(*, project: CompiledProject, key: CompiledObjectKey) -> LineageNode:
    for model in project.models:
        if model.key == key:
            return LineageNode(
                key=key,
                relative_path=str(model.relative_path),
                qualified_name=model.destination.qualified_name,
            )
    for seed in project.seeds:
        if seed.key == key:
            return LineageNode(
                key=key,
                relative_path=str(seed.seed_file.relative_path),
                qualified_name=seed.destination.qualified_name,
            )
    for source in project.sources:
        if source.key == key:
            return LineageNode(
                key=key,
                relative_path=str(source.source_file.relative_path),
                qualified_name=_source_relation_name(source.source_entry),
            )
    return LineageNode(key=key)


def _source_relation_name(source: object) -> str | None:
    database: str | None = getattr(source, "database", None)
    schema: str | None = getattr(source, "schema", None)
    table: str | None = getattr(source, "table", None)
    if table is None:
        return None
    if database is not None and schema is not None:
        return f"{database}.{schema}.{table}"
    if schema is not None:
        return f"{schema}.{table}"
    return table


def _create_schema(*, connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE resources (
            resource_type TEXT NOT NULL,
            resource_name TEXT NOT NULL,
            relative_path TEXT,
            qualified_name TEXT,
            PRIMARY KEY (resource_type, resource_name)
        );
        CREATE TABLE lookups (
            lookup_name TEXT PRIMARY KEY,
            resource_type TEXT NOT NULL,
            resource_name TEXT NOT NULL
        );
        CREATE TABLE edges (
            upstream_type TEXT NOT NULL,
            upstream_name TEXT NOT NULL,
            downstream_type TEXT NOT NULL,
            downstream_name TEXT NOT NULL,
            PRIMARY KEY (upstream_type, upstream_name, downstream_type, downstream_name)
        );
        CREATE INDEX edges_downstream ON edges (downstream_type, downstream_name);
        CREATE INDEX edges_upstream ON edges (upstream_type, upstream_name);
        CREATE TABLE tags (
            tag TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            resource_name TEXT NOT NULL,
            PRIMARY KEY (tag, resource_type, resource_name)
        );
        CREATE TABLE paths (
            resource_type TEXT NOT NULL,
            resource_name TEXT NOT NULL,
            folder TEXT NOT NULL,
            PRIMARY KEY (resource_type, resource_name)
        );
        """
    )


def _write_index(
    *, connection: sqlite3.Connection, fingerprint: str, index: RelationLineageIndex
) -> None:
    connection.executemany(
        "INSERT INTO metadata (key, value) VALUES (?, ?)",
        (
            ("algorithm_version", _CACHE_ALGORITHM_VERSION),
            ("input_fingerprint", fingerprint),
            ("schema_version", str(_CACHE_SCHEMA_VERSION)),
        ),
    )
    connection.executemany(
        "INSERT INTO resources VALUES (?, ?, ?, ?)",
        (
            (str(key.resource_type), key.name, node.relative_path, node.qualified_name)
            for key, node in index.nodes.items()
        ),
    )
    connection.executemany(
        "INSERT INTO lookups VALUES (?, ?, ?)",
        ((name, str(key.resource_type), key.name) for name, key in index.all_keys.items()),
    )
    connection.executemany(
        "INSERT INTO edges VALUES (?, ?, ?, ?)",
        _edge_rows(index=index),
    )
    connection.executemany(
        "INSERT INTO tags VALUES (?, ?, ?)",
        _tag_rows(index=index),
    )
    connection.executemany(
        "INSERT INTO paths VALUES (?, ?, ?)",
        ((str(key.resource_type), key.name, folder) for key, folder in index.path_index.items()),
    )


def _edge_rows(*, index: RelationLineageIndex) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    for downstream, upstreams in index.upstream_deps.items():
        for upstream in upstreams:
            rows.append(
                (
                    str(upstream.resource_type),
                    upstream.name,
                    str(downstream.resource_type),
                    downstream.name,
                )
            )
    return rows


def _tag_rows(*, index: RelationLineageIndex) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for tag, keys in index.tag_index.items():
        for key in keys:
            rows.append((tag, str(key.resource_type), key.name))
    return rows


def _read_index(*, connection: sqlite3.Connection) -> RelationLineageIndex | None:
    resource_rows: list[tuple[str, str, str | None, str | None]] = connection.execute(
        "SELECT resource_type, resource_name, relative_path, qualified_name FROM resources"
    ).fetchall()
    edge_rows: list[tuple[str, str, str, str]] = connection.execute(
        "SELECT upstream_type, upstream_name, downstream_type, downstream_name FROM edges"
    ).fetchall()
    lookup_rows: list[tuple[str, str, str]] = connection.execute(
        "SELECT lookup_name, resource_type, resource_name FROM lookups"
    ).fetchall()
    tag_rows: list[tuple[str, str, str]] = connection.execute(
        "SELECT tag, resource_type, resource_name FROM tags"
    ).fetchall()
    path_rows: list[tuple[str, str, str]] = connection.execute(
        "SELECT resource_type, resource_name, folder FROM paths"
    ).fetchall()
    if (
        sum(map(len, (resource_rows, edge_rows, lookup_rows, tag_rows, path_rows)))
        > _CACHE_MAX_ROWS
    ):
        return None
    keys: dict[tuple[str, str], CompiledObjectKey] = {
        (resource_type, name): CompiledObjectKey(resource_type=resource_type, name=name)
        for resource_type, name, _, _ in resource_rows
    }
    nodes: dict[CompiledObjectKey, LineageNode] = {
        keys[(resource_type, name)]: LineageNode(
            key=keys[(resource_type, name)],
            relative_path=relative_path,
            qualified_name=qualified_name,
        )
        for resource_type, name, relative_path, qualified_name in resource_rows
    }
    upstream_mutable: dict[CompiledObjectKey, list[CompiledObjectKey]] = {}
    downstream_mutable: dict[CompiledObjectKey, list[CompiledObjectKey]] = {}
    for upstream_type, upstream_name, downstream_type, downstream_name in edge_rows:
        upstream: CompiledObjectKey = keys[(upstream_type, upstream_name)]
        downstream: CompiledObjectKey = keys[(downstream_type, downstream_name)]
        upstream_mutable.setdefault(downstream, []).append(upstream)
        downstream_mutable.setdefault(upstream, []).append(downstream)
    tags_mutable: dict[str, set[CompiledObjectKey]] = {}
    for tag, resource_type, name in tag_rows:
        tags_mutable.setdefault(tag, set()).add(keys[(resource_type, name)])
    return RelationLineageIndex(
        nodes=nodes,
        upstream_deps={key: tuple(value) for key, value in upstream_mutable.items()},
        downstream_deps={key: tuple(value) for key, value in downstream_mutable.items()},
        tag_index={tag: frozenset(value) for tag, value in tags_mutable.items()},
        path_index={
            keys[(resource_type, name)]: folder for resource_type, name, folder in path_rows
        },
        all_keys={
            lookup_name: keys[(resource_type, name)]
            for lookup_name, resource_type, name in lookup_rows
        },
    )


def _sqlbuild_version() -> str:
    try:
        return version("sqlbuild")
    except PackageNotFoundError:
        return "0+unknown"
