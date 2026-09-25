"""Map validation SQL locations through normalization and authored macro spans."""

from __future__ import annotations

import re
from dataclasses import replace
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

from sqlbuild.compiler.compile.main.map_expanded_offset import map_expanded_offset
from sqlbuild.compiler.compile.models import CompiledSqlExpansion, MappedOffset
from sqlbuild.compiler.sql_analysis.models import SqlBindingDiagnostic
from sqlbuild.spec.contracts.models import SourceLocation


def get_authored_binding_location(
    *,
    path: Path,
    authored_sql: str,
    authored_query_sql: str,
    cleaned_sql: str,
    diagnostic: SqlBindingDiagnostic,
    expansion: CompiledSqlExpansion | None = None,
) -> SourceLocation | None:
    """Map both native span boundaries through normalization and expansion."""
    line, column = get_authored_binding_position(
        authored_sql=authored_sql,
        authored_query_sql=authored_query_sql,
        cleaned_sql=cleaned_sql,
        diagnostic=diagnostic,
        expansion=expansion,
    )
    if line is None or column is None:
        return None
    end_line: int | None = None
    end_column: int | None = None
    if diagnostic.end is not None:
        end_line, end_column = get_authored_binding_position(
            authored_sql=authored_sql,
            authored_query_sql=authored_query_sql,
            cleaned_sql=cleaned_sql,
            expansion=expansion,
            diagnostic=replace(
                diagnostic, message="", start=diagnostic.end, line=None, column=None
            ),
        )
    return SourceLocation(
        path=path, line=line, column=column, end_line=end_line, end_column=end_column
    )


def get_authored_binding_position(
    *,
    authored_sql: str,
    authored_query_sql: str,
    cleaned_sql: str,
    diagnostic: SqlBindingDiagnostic,
    expansion: CompiledSqlExpansion | None = None,
) -> tuple[int | None, int | None]:
    """Prefer authored identifier evidence; anchor span-less errors at the query."""
    match: re.Match[str] | None = re.search(
        r"(?:Unknown column|Ambiguous column reference|JOIN USING column) '([^']+)'",
        diagnostic.message,
    )
    if match is not None:
        identifier: str = match.group(1).rsplit(".", maxsplit=1)[-1]
        occurrences: list[re.Match[str]] = list(
            re.finditer(rf"(?<!\w){re.escape(identifier)}(?!\w)", authored_sql)
        )
        if len(occurrences) == 1:
            return _position(text=authored_sql, offset=occurrences[0].start())
    query_start: int = authored_sql.find(authored_query_sql)
    if query_start < 0:
        return None, None
    offset: int | None = diagnostic.start
    if offset is None and diagnostic.line is not None and diagnostic.column is not None:
        lines: list[str] = cleaned_sql.splitlines(keepends=True)
        offset = sum(len(line) for line in lines[: diagnostic.line - 1]) + diagnostic.column - 1
    if offset is None:
        return _position(text=authored_sql, offset=query_start)
    expanded_sql: str = expansion.expanded_sql if expansion is not None else authored_query_sql
    expanded_offset: int = _normalized_offset(
        original=expanded_sql, normalized=cleaned_sql, offset=offset
    )
    mapped: MappedOffset = map_expanded_offset(
        offset=expanded_offset, passes=expansion.passes if expansion is not None else ()
    )
    return _position(text=authored_sql, offset=query_start + mapped.offset)


def _normalized_offset(*, original: str, normalized: str, offset: int) -> int:
    if original == normalized:
        return offset
    for original_start, original_end, normalized_start, normalized_end in _normalization_map(
        original=original, normalized=normalized
    ):
        if offset < normalized_start:
            return original_start
        if normalized_start <= offset <= normalized_end:
            return original_start + min(offset - normalized_start, original_end - original_start)
    return len(original)


@lru_cache(maxsize=32)
def _normalization_map(*, original: str, normalized: str) -> tuple[tuple[int, int, int, int], ...]:
    """Align SQL tokens once, avoiding quadratic character matching on repetitive queries."""
    original_tokens: list[re.Match[str]] = list(re.finditer(r"\w+|[^\w\s]", original))
    normalized_tokens: list[re.Match[str]] = list(re.finditer(r"\w+|[^\w\s]", normalized))
    matcher: SequenceMatcher[str] = SequenceMatcher(
        a=[token.group().casefold() for token in original_tokens],
        b=[token.group().casefold() for token in normalized_tokens],
        autojunk=True,
    )
    mappings: list[tuple[int, int, int, int]] = []
    for block in matcher.get_matching_blocks():
        for index in range(block.size):
            source: re.Match[str] = original_tokens[block.a + index]
            target: re.Match[str] = normalized_tokens[block.b + index]
            mappings.append((source.start(), source.end(), target.start(), target.end()))
    return tuple(mappings)


def _position(*, text: str, offset: int) -> tuple[int, int]:
    return text.count("\n", 0, offset) + 1, offset - text.rfind("\n", 0, offset)
