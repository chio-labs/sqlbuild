"""Offsets, positions, and edit application for authored text."""

from __future__ import annotations

import re
from functools import cache

from sqlbuild.compiler.refactoring.constants import IDENTIFIER_CHARACTERS, NON_CODE_PATTERN
from sqlbuild.compiler.refactoring.exceptions import RefactorEditError
from sqlbuild.compiler.refactoring.models import (
    FileChange,
    ManualLocation,
    MigrationDeclaration,
    RefactorParts,
    RefactorPlan,
    RefactorRequest,
    TextEdit,
)
from sqlbuild.compiler.refactoring.types import EditKind


def line_column(*, text: str, offset: int) -> tuple[int, int]:
    """Return the 1-based line and column of an offset."""

    line_start: int = text.rfind("\n", 0, offset) + 1
    return text.count("\n", 0, offset) + 1, offset - line_start + 1


def text_edit(
    *,
    text: str,
    start: int,
    end: int,
    replacement: str,
    kind: EditKind,
    before: str | None = None,
    after: str | None = None,
) -> TextEdit:
    """Build one edit with its position and display text."""

    line: int
    column: int
    line, column = line_column(text=text, offset=start)
    return TextEdit(
        start=start,
        end=end,
        replacement=replacement,
        kind=kind,
        line=line,
        column=column,
        before=text[start:end] if before is None else before,
        after=replacement.strip() if after is None else after,
    )


def manual_at(*, path: str, text: str, offset: int | None, reason: str) -> ManualLocation:
    """Build a manual location at an optional offset."""

    if offset is None:
        return ManualLocation(path=path, line=None, column=None, reason=reason)
    line: int
    column: int
    line, column = line_column(text=text, offset=offset)
    return ManualLocation(path=path, line=line, column=column, reason=reason)


def apply_text_edits(*, text: str, edits: tuple[TextEdit, ...]) -> str:
    """Apply non-overlapping edits back to front; identical duplicates apply once."""

    unique: list[TextEdit] = sorted(
        {(edit.start, edit.end, edit.replacement): edit for edit in edits}.values(),
        key=lambda edit: (edit.start, edit.end),
        reverse=True,
    )
    result: str = text
    previous_start: int = len(text) + 1
    edit: TextEdit
    for edit in unique:
        if edit.end > previous_start:
            raise RefactorEditError(f"overlapping refactoring edits at offset {edit.start}")
        result = result[: edit.start] + edit.replacement + result[edit.end :]
        previous_start = edit.start
    return result


def merge_parts(*, parts: tuple[RefactorParts, ...]) -> RefactorParts:
    """Concatenate planning parts in order."""

    edits: list[tuple[str, TextEdit]] = []
    manual: list[ManualLocation] = []
    blocking: list[ManualLocation] = []
    migrations: list[MigrationDeclaration] = []
    cascaded: list[str] = []
    part: RefactorParts
    for part in parts:
        edits.extend(part.edits)
        manual.extend(part.manual)
        blocking.extend(part.blocking)
        migrations.extend(part.migrations)
        cascaded.extend(part.cascaded)
    return RefactorParts(
        edits=tuple(edits),
        manual=tuple(manual),
        blocking=tuple(blocking),
        migrations=tuple(migrations),
        cascaded=tuple(cascaded),
    )


def path_edits(*, path: str, edits: tuple[TextEdit, ...]) -> tuple[tuple[str, TextEdit], ...]:
    """Attach a file path to each edit."""

    return tuple((path, edit) for edit in edits)


def file_changes(
    *, edits: tuple[tuple[str, TextEdit], ...], moves: dict[str, str]
) -> tuple[FileChange, ...]:
    """Group edits by file, move files, and order the result by final path."""

    grouped: dict[str, list[TextEdit]] = {path: [] for path in moves}
    path: str
    edit: TextEdit
    for path, edit in edits:
        grouped.setdefault(path, []).append(edit)
    return tuple(
        sorted(
            (
                FileChange(path=moves.get(path, path), original_path=path, edits=tuple(items))
                for path, items in grouped.items()
            ),
            key=lambda change: change.path,
        )
    )


def build_plan(
    *,
    request: RefactorRequest,
    parts: RefactorParts,
    moves: dict[str, str],
    renamed_columns: tuple[tuple[str, str, str], ...] = (),
    help: str | None = None,
) -> RefactorPlan:
    """Assemble a plan from merged parts; help applies only when manual locations exist."""

    return RefactorPlan(
        request=request,
        changes=file_changes(edits=parts.edits, moves=moves),
        manual=parts.manual,
        blocking=parts.blocking,
        migrations=parts.migrations,
        renamed_columns=renamed_columns,
        help=help if parts.manual else None,
    )


def identifier_sites(*, text: str, names: frozenset[str]) -> tuple[tuple[int, int, str], ...]:
    """Return unquoted identifier tokens matching names, outside comments and strings."""

    if not names:
        return ()
    lowered: dict[str, str] = {name.lower(): name for name in names}
    sites: list[tuple[int, int, str]] = []
    match: re.Match[str]
    for match in _identifier_pattern(frozenset(lowered)).finditer(text):
        token: str | None = match.group("identifier")
        if token is not None:
            sites.append(
                (match.start("identifier"), match.end("identifier"), lowered[token.lower()])
            )
    return tuple(sites)


def whole_word_offsets(*, text: str, word: str) -> tuple[int, ...]:
    """Return the offsets of a case-insensitive whole identifier word anywhere in text."""

    pattern: re.Pattern[str] = re.compile(
        rf"(?<![{IDENTIFIER_CHARACTERS}]){re.escape(word)}(?![{IDENTIFIER_CHARACTERS}])", re.I
    )
    return tuple(match.start() for match in pattern.finditer(text))


@cache
def _identifier_pattern(names: frozenset[str]) -> re.Pattern[str]:
    ordered: list[str] = sorted(names, key=lambda name: (-len(name), name))
    alternatives: str = "|".join(re.escape(name) for name in ordered)
    return re.compile(
        NON_CODE_PATTERN
        + rf"|(?<![{IDENTIFIER_CHARACTERS}])(?P<identifier>{alternatives})"
        + rf"(?![{IDENTIFIER_CHARACTERS}])",
        re.I,
    )
