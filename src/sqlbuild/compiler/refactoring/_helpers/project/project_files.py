"""Authored project files and SQL bodies a refactoring reads and edits."""

from __future__ import annotations

import ast
from pathlib import Path

from sqlbuild.compiler.discovery.models import (
    DiscoveredAuditBlock,
    DiscoveredProjectInputs,
    DiscoveredSqlTestBlock,
)
from sqlbuild.compiler.refactoring._helpers.text.text_edits import whole_word_offsets
from sqlbuild.compiler.refactoring.constants import SQL_LIKE_PATTERN
from sqlbuild.compiler.refactoring.models import AuthoredBody, ManualLocation, ProjectSqlFile
from sqlbuild.compiler.refactoring.types import SqlFileRole

type _AuthoredFile = tuple[SqlFileRole, Path, str, tuple[str, ...]]


def project_sql_files(*, discovered: DiscoveredProjectInputs) -> tuple[ProjectSqlFile, ...]:
    """Return every discovered SQL file with its authored contents."""

    files: dict[str, ProjectSqlFile] = {}
    role: SqlFileRole
    relative_path: Path
    contents: str
    for role, relative_path, contents, _ in (
        *_model_files(discovered=discovered),
        *_authored_files(discovered=discovered),
    ):
        relative: str = relative_path.as_posix()
        files.setdefault(
            relative, ProjectSqlFile(relative_path=relative, contents=contents, role=role)
        )
    return tuple(files[path] for path in sorted(files))


def yaml_files(*, discovered: DiscoveredProjectInputs) -> tuple[ProjectSqlFile, ...]:
    """Return every source and seed YAML declaration file."""

    files: dict[str, str] = {
        item.relative_path.as_posix(): item.contents
        for item in (*discovered.source_files, *discovered.schema_files)
    }
    return tuple(
        ProjectSqlFile(relative_path=path, contents=files[path], role=SqlFileRole.YAML)
        for path in sorted(files)
    )


def authored_bodies(*, discovered: DiscoveredProjectInputs) -> tuple[AuthoredBody, ...]:
    """Locate every non-model SQL body in its file, in file order."""

    bodies: list[AuthoredBody] = []
    role: SqlFileRole
    relative_path: Path
    contents: str
    texts: tuple[str, ...]
    for role, relative_path, contents, texts in _authored_files(discovered=discovered):
        cursor: int = 0
        text: str
        for text in texts:
            start: int = contents.find(text, cursor) if text.strip() else -1
            if start < 0:
                continue
            cursor = start + len(text)
            bodies.append(
                AuthoredBody(
                    path=relative_path.as_posix(),
                    role=role,
                    contents=contents,
                    start=start,
                    text=text,
                )
            )
    return tuple(bodies)


def python_string_locations(
    *,
    project_dir: Path,
    discovered: DiscoveredProjectInputs,
    names: tuple[str, ...],
    reason: str,
    context: str | None = None,
) -> tuple[ManualLocation, ...]:
    """Flag Python strings that name a model or column; with context, only SQL naming it too."""

    locations: list[ManualLocation] = []
    relative_path: Path
    for relative_path in _python_paths(discovered=discovered):
        locations.extend(
            _string_locations(
                project_dir=project_dir,
                relative_path=relative_path,
                names=names,
                reason=reason,
                context=context,
            )
        )
    return tuple(locations)


def _model_files(*, discovered: DiscoveredProjectInputs) -> tuple[_AuthoredFile, ...]:
    return tuple(
        (SqlFileRole.MODEL, item.relative_path, item.contents, ())
        for item in discovered.model_files
    )


def _authored_files(*, discovered: DiscoveredProjectInputs) -> tuple[_AuthoredFile, ...]:
    files: list[_AuthoredFile] = []
    files.extend(
        (SqlFileRole.TEST, item.relative_path, item.contents, _test_bodies(item.blocks))
        for item in discovered.test_files
    )
    files.extend(
        (SqlFileRole.SCENARIO, item.relative_path, item.contents, (item.sql_body,))
        for item in discovered.scenario_files
    )
    files.extend(
        (SqlFileRole.AUDIT, item.relative_path, item.contents, _audit_bodies(item.blocks))
        for item in discovered.audit_files
    )
    files.extend(
        (SqlFileRole.HOOK, item.relative_path, item.contents, (item.sql_body,))
        for item in discovered.sql_hook_files
    )
    files.extend(
        (SqlFileRole.FUNCTION, item.relative_path, item.contents, (item.body_sql,))
        for item in discovered.sql_function_files
    )
    files.extend(
        (SqlFileRole.SCHEMA, item.relative_path, item.contents, ())
        for item in discovered.model_schema_files
    )
    return tuple(files)


def _test_bodies(blocks: tuple[DiscoveredSqlTestBlock, ...]) -> tuple[str, ...]:
    return tuple(block.sql_body for block in blocks)


def _audit_bodies(blocks: tuple[DiscoveredAuditBlock, ...]) -> tuple[str, ...]:
    return tuple(block.sql_body for block in blocks)


def _python_paths(*, discovered: DiscoveredProjectInputs) -> tuple[Path, ...]:
    paths: set[Path] = set()
    paths.update(item.relative_path for item in discovered.loader_functions)
    paths.update(item.relative_path for item in discovered.task_functions)
    paths.update(item.relative_path for item in discovered.asset_functions)
    paths.update(item.relative_path for item in discovered.check_functions)
    paths.update(item.relative_path for item in discovered.hook_functions)
    paths.update(item.relative_path for item in discovered.audit_factories)
    paths.update(item.relative_path for item in discovered.python_function_files)
    paths.update(item.relative_path for item in discovered.materialization_files)
    return tuple(sorted(paths))


def _string_locations(
    *,
    project_dir: Path,
    relative_path: Path,
    names: tuple[str, ...],
    reason: str,
    context: str | None,
) -> tuple[ManualLocation, ...]:
    try:
        tree: ast.Module = ast.parse((project_dir / relative_path).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeError):
        return ()
    locations: list[ManualLocation] = []
    node: ast.AST
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if _flags(value=node.value, names=names, context=context):
            locations.append(
                ManualLocation(
                    path=relative_path.as_posix(),
                    line=node.lineno,
                    column=node.col_offset + 1,
                    reason=reason,
                )
            )
    return tuple(locations)


def _flags(*, value: str, names: tuple[str, ...], context: str | None) -> bool:
    sql_like: bool = bool(SQL_LIKE_PATTERN.search(value))
    if context is not None and not (sql_like and whole_word_offsets(text=value, word=context)):
        return False
    return any(
        value.strip().lower() == name.lower()
        or (sql_like and bool(whole_word_offsets(text=value, word=name)))
        for name in names
    )
