"""Scanner that locates DSL header regions inside SQL files."""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path, PurePath

from sqlbuild.compiler.compile.constants import HOOK_DIRECTORY_NAME
from sqlbuild.compiler.discovery.main.named_declaration_role_kind import (
    named_declaration_role_kind,
)
from sqlbuild.compiler.scopes.types import DeclarationKind
from sqlbuild.lint.constants import DSL_HEADER_KINDS
from sqlbuild.lint.models import HeaderSpan, LintFileRole

_QUOTE_CHARACTERS: frozenset[str] = frozenset({"'", '"'})
_ESCAPE_CHARACTER: str = "\\"
_OPEN_PAREN: str = "("
_CLOSE_PAREN: str = ")"
_STATEMENT_TERMINATOR: str = ";"
_UNQUOTED_HEADER_TOKEN: re.Pattern[str] = re.compile(r"""[()'"]""")
_QUOTED_HEADER_TOKENS: dict[str, re.Pattern[str]] = {
    quote: re.compile(rf"[\\{quote}]") for quote in _QUOTE_CHARACTERS
}


def scan_headers(*, contents: str, first_only: bool = False) -> tuple[HeaderSpan, ...]:
    """Return all DSL header spans found in the file contents."""

    return _scan_delimited_regions(contents=contents, kinds=DSL_HEADER_KINDS, first_only=first_only)


def lint_file_role(
    *, file_path: Path, project_dir: Path, relative_path: PurePath | None = None
) -> LintFileRole:
    """Return the path facts lint needs, reusing a caller's project-relative path."""

    if relative_path is None:
        if not file_path.is_relative_to(project_dir):
            return LintFileRole()
        relative_path = file_path.relative_to(project_dir)
    return LintFileRole(
        declaration_kind=named_declaration_role_kind(relative_path=relative_path),
        in_project=True,
        in_hook_directory=relative_path.is_relative_to(HOOK_DIRECTORY_NAME),
    )


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
    role: LintFileRole | None = None,
) -> tuple[tuple[int, int], ...]:
    """Return lintable authored bodies using resource-specific DSL boundaries."""

    file_role: LintFileRole = (
        role if role is not None else lint_file_role(file_path=file_path, project_dir=project_dir)
    )
    if file_role.in_project and file_role.declaration_kind in {
        DeclarationKind.AUDIT,
        DeclarationKind.SINGULAR_AUDIT,
    }:
        measurement_ranges: tuple[tuple[int, int], ...] = measurement_body_ranges(contents=contents)
        if measurement_ranges:
            return measurement_ranges
    return sql_body_ranges(contents=contents, headers=headers)


def _scan_delimited_regions(
    *, contents: str, kinds: frozenset[str], first_only: bool = False
) -> tuple[HeaderSpan, ...]:
    """Return line-leading parenthesized regions with one of the requested names."""

    spans: list[HeaderSpan] = []
    covered_until: int = 0
    match: re.Match[str]
    for match in _delimited_region_pattern(kinds).finditer(contents):
        kind: str | None = match.group("kind")
        if kind is None:
            continue
        keyword_start: int = match.start("kind")
        if keyword_start < covered_until:
            continue
        span: HeaderSpan | None = _match_header_span(
            contents=contents,
            kind=kind,
            keyword_start=keyword_start,
            body_start=match.end("kind"),
        )
        if span is not None:
            spans.append(span)
            covered_until = span.end
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
    match: re.Match[str] | None
    while True:
        match = (
            _UNQUOTED_HEADER_TOKEN if in_quote is None else _QUOTED_HEADER_TOKENS[in_quote]
        ).search(contents, index)
        if match is None:
            return None
        index = match.start()
        character: str = contents[index]
        if in_quote is not None:
            if character == _ESCAPE_CHARACTER:
                index += 2
                continue
            in_quote = None
        elif character in _QUOTE_CHARACTERS:
            in_quote = character
        elif character == _OPEN_PAREN:
            depth += 1
        else:
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
