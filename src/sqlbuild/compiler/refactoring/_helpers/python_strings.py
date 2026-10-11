"""Python `ast` scan for strings that name a renamed model or column."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.refactoring.constants import IDENTIFIER_CHARACTERS, SQL_LIKE_PATTERN
from sqlbuild.compiler.refactoring.models import ManualLocation


def python_paths(*, discovered: DiscoveredProjectInputs) -> tuple[Path, ...]:
    """Return the project Python files discovery found, sorted."""

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


def string_locations(
    *,
    project_dir: Path,
    relative_path: Path,
    names: tuple[str, ...],
    reason: str,
    context: str | None,
) -> tuple[ManualLocation, ...]:
    """Return the string constants of one Python file that name a renamed model or column."""

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
    if context is not None and not (sql_like and _has_word(text=value, word=context)):
        return False
    return any(
        value.strip().lower() == name.lower() or (sql_like and _has_word(text=value, word=name))
        for name in names
    )


def _has_word(*, text: str, word: str) -> bool:
    pattern: re.Pattern[str] = re.compile(
        rf"(?<![{IDENTIFIER_CHARACTERS}]){re.escape(word)}(?![{IDENTIFIER_CHARACTERS}])", re.I
    )
    return pattern.search(text) is not None
