"""Scanner that locates DSL header regions inside SQL files."""

from __future__ import annotations

from sqlbuild.lint.constants import DSL_HEADER_KINDS, IDENTIFIER_SEPARATOR_CHARACTER
from sqlbuild.lint.models import HeaderSpan

_QUOTE_CHARACTERS: frozenset[str] = frozenset({"'", '"'})
_ESCAPE_CHARACTER: str = "\\"
_OPEN_PAREN: str = "("
_CLOSE_PAREN: str = ")"
_STATEMENT_TERMINATOR: str = ";"
_NEWLINE: str = "\n"


def scan_headers(*, contents: str) -> tuple[HeaderSpan, ...]:
    """Return all DSL header spans found in the file contents."""

    spans: list[HeaderSpan] = []
    index: int = 0
    length: int = len(contents)
    while index < length:
        character: str = contents[index]
        if not (character.isalpha() or character == IDENTIFIER_SEPARATOR_CHARACTER):
            index += 1
            continue
        word_end: int = _word_end(contents=contents, start=index)
        kind: str = contents[index:word_end]
        if (
            kind not in DSL_HEADER_KINDS
            or _is_word_prefix(contents=contents, start=index)
            or not _is_line_start(contents=contents, start=index)
        ):
            index = word_end
            continue
        span: HeaderSpan | None = _match_header_span(
            contents=contents,
            kind=kind,
            keyword_start=index,
            body_start=word_end,
        )
        if span is None:
            index = word_end
            continue
        spans.append(span)
        index = span.end
    return tuple(spans)


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


def _word_end(*, contents: str, start: int) -> int:
    index: int = start
    length: int = len(contents)
    while index < length and (
        contents[index].isalnum() or contents[index] == IDENTIFIER_SEPARATOR_CHARACTER
    ):
        index += 1
    return index


def _is_word_prefix(*, contents: str, start: int) -> bool:
    if start == 0:
        return False
    previous: str = contents[start - 1]
    return previous.isalnum() or previous == IDENTIFIER_SEPARATOR_CHARACTER


def _is_line_start(*, contents: str, start: int) -> bool:
    line_start: int = contents.rfind(_NEWLINE, 0, start) + 1
    prefix: str = contents[line_start:start]
    return all(character.isspace() for character in prefix)


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
