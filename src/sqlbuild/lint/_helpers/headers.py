"""Scanner that locates DSL header regions inside SQL files."""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

from sqlbuild.compiler.compile.constants import AUDIT_DIRECTORY_NAME
from sqlbuild.lint.constants import DSL_HEADER_KINDS
from sqlbuild.lint.models import HeaderSpan

_QUOTE_CHARACTERS: frozenset[str] = frozenset({"'", '"'})
_ESCAPE_CHARACTER: str = "\\"
_OPEN_PAREN: str = "("
_CLOSE_PAREN: str = ")"
_STATEMENT_TERMINATOR: str = ";"


def scan_headers(*, contents: str, first_only: bool = False) -> tuple[HeaderSpan, ...]:
    """Return all DSL header spans found in the file contents."""

    return _scan_delimited_regions(contents=contents, kinds=DSL_HEADER_KINDS, first_only=first_only)


def measurement_body_ranges(*, contents: str) -> tuple[tuple[int, int], ...]:
    """Return authored query ranges inside MEASURE and EVIDENCE blocks."""

    blocks: tuple[HeaderSpan, ...] = _scan_delimited_regions(
        contents=contents, kinds=frozenset({"MEASURE", "EVIDENCE"})
    )
    ranges: list[tuple[int, int]] = []
    for block in blocks:
        opening_index: int = contents.find(_OPEN_PAREN, block.start, block.end)
        closing_index: int = contents.rfind(_CLOSE_PAREN, opening_index + 1, block.end)
        body_start: int = _first_non_whitespace(
            contents=contents, start=opening_index + 1, end=closing_index
        )
        if body_start < closing_index:
            ranges.append((body_start, closing_index))
    return tuple(ranges)


def lint_body_ranges(
    *,
    contents: str,
    headers: tuple[HeaderSpan, ...],
    file_path: Path,
    project_dir: Path,
) -> tuple[tuple[int, int], ...]:
    """Return lintable authored bodies using resource-specific DSL boundaries."""

    if file_path.is_relative_to(project_dir / AUDIT_DIRECTORY_NAME):
        measurement_ranges: tuple[tuple[int, int], ...] = measurement_body_ranges(contents=contents)
        if measurement_ranges:
            return measurement_ranges
    return sql_body_ranges(contents=contents, headers=headers)


def _scan_delimited_regions(
    *, contents: str, kinds: frozenset[str], first_only: bool = False
) -> tuple[HeaderSpan, ...]:
    """Return line-leading parenthesized regions with one of the requested names."""

    spans: list[HeaderSpan] = []
    match: re.Match[str]
    for match in _delimited_region_pattern(kinds).finditer(contents):
        kind: str | None = match.group("kind")
        if kind is None:
            continue
        keyword_start: int = match.start("kind")
        span: HeaderSpan | None = _match_header_span(
            contents=contents,
            kind=kind,
            keyword_start=keyword_start,
            body_start=match.end("kind"),
        )
        if span is not None:
            spans.append(span)
            if first_only:
                break
    return tuple(spans)


@cache
def _delimited_region_pattern(kinds: frozenset[str]) -> re.Pattern[str]:
    """Build a C-level scanner that skips comments and SQL strings."""

    kind_alternatives: str = "|".join(re.escape(kind) for kind in sorted(kinds))
    return re.compile(
        rf"--[^\n]*(?:\n|\Z)"
        rf"|/\*[\s\S]*?(?:\*/|\Z)"
        rf"|'(?:''|[^'])*(?:'|\Z)"
        rf'|"(?:""|[^"])*(?:"|\Z)'
        rf"|(?m:^[^\S\r\n]*(?P<kind>{kind_alternatives})\b)"
    )


def sql_body_ranges(
    *, contents: str, headers: tuple[HeaderSpan, ...]
) -> tuple[tuple[int, int], ...]:
    """Return non-empty SQL body ranges between consecutive headers."""

    ranges: list[tuple[int, int]] = []
    cursor: int = 0
    header: HeaderSpan
    for header in headers:
        body_start: int = _first_non_whitespace(contents=contents, start=cursor, end=header.start)
        if body_start < header.start:
            ranges.append((body_start, header.start))
        cursor = header.end
    tail_start: int = _first_non_whitespace(contents=contents, start=cursor, end=len(contents))
    if tail_start < len(contents):
        ranges.append((tail_start, len(contents)))
    return tuple(ranges)


def _match_header_span(
    *, contents: str, kind: str, keyword_start: int, body_start: int
) -> HeaderSpan | None:
    index: int = _skip_whitespace(contents=contents, index=body_start)
    if index >= len(contents) or contents[index] != _OPEN_PAREN:
        return None
    depth: int = 0
    in_quote: str | None = None
    length: int = len(contents)
    while index < length:
        character: str = contents[index]
        if in_quote is not None:
            if character == _ESCAPE_CHARACTER:
                index += 2
                continue
            if character == in_quote:
                in_quote = None
            index += 1
            continue
        if character in _QUOTE_CHARACTERS:
            in_quote = character
            index += 1
            continue
        if character == _OPEN_PAREN:
            depth += 1
        elif character == _CLOSE_PAREN:
            depth -= 1
            if depth == 0:
                terminator_index: int = _skip_whitespace(contents=contents, index=index + 1)
                span_end: int = index + 1
                if (
                    terminator_index < len(contents)
                    and contents[terminator_index] == _STATEMENT_TERMINATOR
                ):
                    span_end = terminator_index + 1
                return HeaderSpan(kind=kind, start=keyword_start, end=span_end)
        index += 1
    return None


def _skip_whitespace(*, contents: str, index: int) -> int:
    length: int = len(contents)
    while index < length and contents[index].isspace():
        index += 1
    return index


def _first_non_whitespace(*, contents: str, start: int, end: int) -> int:
    index: int = start
    while index < end:
        if not contents[index].isspace():
            return index
        index += 1
    return end
