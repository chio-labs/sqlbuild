"""Point repeated long literals at one shared constant in the nearest common folder."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path, PurePosixPath

from sqlbuild.rule_engine.models import Finding

_LONG_LITERAL_CODE: str = "SQBRSQL044"
_QUOTE: str = "'"
_LISTED_PATHS: int = 5
_MIN_SHARED_FILES: int = 2
_MIN_SCOPED_FOLDER_DEPTH: int = 2
_DECLARATION_GROUP: str = "_sqlbuild"
_LOCAL_CONSTANTS: str = "_sqlbuild/_constants/"
_INHERITED_CONSTANTS: str = "_sqlbuild/constants/"
_PROJECT_CONSTANTS: str = "constants/"


def with_duplicate_literal_hints(
    *, findings: tuple[Finding, ...], project_dir: Path
) -> tuple[Finding, ...]:
    """Prefix SQBRSQL044 help with the other files that repeat the identical literal."""

    texts: dict[Path, list[str]] = {}
    literals: dict[int, str] = {}
    for index, finding in enumerate(findings):
        if finding.code != _LONG_LITERAL_CODE or finding.unevaluated:
            continue
        literal: str | None = _literal_at(
            lines=_lines(texts=texts, path=project_dir / finding.path),
            line=finding.line,
            column=finding.column,
        )
        if literal is not None:
            literals[index] = literal
    paths_by_literal: dict[str, set[PurePosixPath]] = {}
    for index, literal in literals.items():
        paths_by_literal.setdefault(literal, set()).add(PurePosixPath(findings[index].path))
    hinted: list[Finding] = list(findings)
    for index, literal in literals.items():
        paths: set[PurePosixPath] = paths_by_literal[literal]
        if len(paths) < _MIN_SHARED_FILES:
            continue
        own: PurePosixPath = PurePosixPath(findings[index].path)
        hint: str = _hint(others=sorted(paths - {own}), every=paths)
        hinted[index] = replace(
            findings[index], remediation=f"{hint} {findings[index].remediation}"
        )
    return tuple(hinted)


def _lines(*, texts: dict[Path, list[str]], path: Path) -> list[str]:
    if path not in texts:
        try:
            texts[path] = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            texts[path] = []
    return texts[path]


def _literal_at(*, lines: list[str], line: int, column: int) -> str | None:
    """The single-quoted literal starting at a 1-based position, quotes included."""

    if not 1 <= line <= len(lines):
        return None
    text: str = lines[line - 1]
    start: int = column - 1
    if start < 0 or text[start : start + 1] != _QUOTE:
        return None
    position: int = start + 1
    while position < len(text):
        if text[position] == _QUOTE:
            if text[position + 1 : position + 2] == _QUOTE:
                position += 2
                continue
            return text[start : position + 1]
        position += 1
    return None


def _hint(*, others: list[PurePosixPath], every: set[PurePosixPath]) -> str:
    listed: str = ", ".join(path.as_posix() for path in others[:_LISTED_PATHS])
    more: str = f" and {len(others) - _LISTED_PATHS} more" if len(others) > _LISTED_PATHS else ""
    owners: set[PurePosixPath] = {_owner(path) for path in every}
    common: PurePosixPath = _common_folder(owners)
    if len(common.parts) < _MIN_SCOPED_FOLDER_DEPTH:
        placement: str = (
            f"no folder below the project roots holds every use, so declare it once in "
            f"top-level `{_PROJECT_CONSTANTS}`"
        )
    else:
        directory: str = _LOCAL_CONSTANTS if owners == {common} else _INHERITED_CONSTANTS
        placement = (
            f"their nearest common folder is `{common.as_posix()}`, so declare it once in "
            f"`{common.as_posix()}/{directory}`"
        )
    return (
        f"The identical literal also appears in {listed}{more}; {placement} "
        "and reference it with `@const` in each file."
    )


def _owner(path: PurePosixPath) -> PurePosixPath:
    """The folder whose declarations a file sees: above `_sqlbuild/`, else its own folder."""

    if _DECLARATION_GROUP in path.parts:
        return PurePosixPath(*path.parts[: path.parts.index(_DECLARATION_GROUP)])
    return path.parent


def _common_folder(folders: set[PurePosixPath]) -> PurePosixPath:
    return PurePosixPath(os.path.commonpath([folder.as_posix() for folder in folders]))
