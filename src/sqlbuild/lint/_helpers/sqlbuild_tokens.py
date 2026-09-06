"""Neutralize SQLBuild interpolation for native SQL analysis and formatting."""

from __future__ import annotations

import re

from sqlbuild.compiler.compile.constants import (
    MACRO_TOKEN,
    SQL_ARGUMENT_QUOTED_PARAMETER_PATTERN,
    SQL_ARGUMENT_RAW_PARAMETER_PATTERN,
    SQL_INTERPOLATION_TOKEN,
)
from sqlbuild.compiler.compile.models import ExpansionSpan
from sqlbuild.lint.constants import (
    CLOSING_PAREN_CHARACTER,
    EXPECTED_SENTINEL_OCCURRENCES,
    IDENTIFIER_EXTRA_CHARACTER,
    INTERPOLATION_NAME_EXTRA_CHARACTERS,
    OPENING_PAREN_CHARACTER,
    SENTINEL_TEMPLATE,
    SINGLE_QUOTE_CHARACTER,
    SQL_ESCAPE_CHARACTER,
    SQL_QUOTE_CHARACTERS,
    TEMPLATE_INTERPOLATION_END,
    TEMPLATE_INTERPOLATION_START,
)
from sqlbuild.lint.exceptions import InterpolationRestorationError
from sqlbuild.lint.models import InterpolationSite

_SQLBUILD_FUNCTION_NAMES: tuple[str, ...] = (
    "__dbt_ref",
    "__table_fn",
    "__source",
    "__seed",
    "__udf",
    "__ref",
)
_AUDIT_PARAMETER_SENTINEL_TEMPLATE: str = "__sqlbuild_audit_parameter_{index}__"
_CONTEXT_SENTINEL_TEMPLATE: str = "__sqlbuild_context_parameter_{index}__"
_LINE_COMMENT_START: str = "--"
_BLOCK_COMMENT_START: str = "/*"
_BLOCK_COMMENT_END: str = "*/"
_TABLE_FUNCTION_INTRINSIC_NAME: str = "__table_fn"
_SQLBUILD_FUNCTION_PATTERN: str = "|".join(
    re.escape(name) for name in sorted(_SQLBUILD_FUNCTION_NAMES)
)
_INTERPOLATION_SCAN_PATTERN: re.Pattern[str] = re.compile(
    rf"--[^\n]*(?:\n|\Z)"
    rf"|/\*[\s\S]*?(?:\*/|\Z)"
    rf"|'(?:\\.|''|[^'\\])*(?:'|\Z)"
    rf'|"(?:\\.|""|[^"\\])*(?:"|\Z)'
    rf"|(?P<site>@@|\$\{{|@|(?:{_SQLBUILD_FUNCTION_PATTERN})\s*\()"
)


def neutralize_context_interpolation(*, body: str) -> tuple[str, tuple[InterpolationSite, ...]]:
    """Replace runtime CTX interpolation with parseable generated sentinels."""

    sites: list[InterpolationSite] = []
    pieces: list[str] = []
    output_length: int = 0
    copied_to: int = 0
    token: str = f"{SQL_INTERPOLATION_TOKEN}CTX:"
    while True:
        start: int = body.find(token, copied_to)
        if start < 0:
            break
        end: int | None = _interpolation_site_end(body=body, start=start)
        if end is None:
            break
        literal: str = body[copied_to:start]
        sentinel: str = _CONTEXT_SENTINEL_TEMPLATE.format(index=len(sites))
        pieces.extend((literal, sentinel))
        output_length += len(literal)
        sites.append(
            InterpolationSite(
                sentinel=sentinel,
                neutralized_start=output_length,
                neutralized_end=output_length + len(sentinel),
                original_start=start,
                original_end=end,
                original_text=body[start:end],
            )
        )
        output_length += len(sentinel)
        copied_to = end
    pieces.append(body[copied_to:])
    return "".join(pieces), tuple(sites)


def neutralize_generic_audit_parameters(*, body: str) -> tuple[str, tuple[InterpolationSite, ...]]:
    """Replace unbound generic-audit arguments with parseable generated sentinels."""

    matches: list[tuple[int, int, bool]] = []
    for match in SQL_ARGUMENT_QUOTED_PARAMETER_PATTERN.finditer(body):
        matches.append((match.start(), match.end(), True))
    for match in SQL_ARGUMENT_RAW_PARAMETER_PATTERN.finditer(body):
        matches.append((match.start(), match.end(), False))
    matches.sort(key=lambda item: item[0])

    sites: list[InterpolationSite] = []
    pieces: list[str] = []
    output_length: int = 0
    copied_to: int = 0
    for start, end, quoted in matches:
        literal: str = body[copied_to:start]
        identifier: str = _AUDIT_PARAMETER_SENTINEL_TEMPLATE.format(index=len(sites))
        sentinel: str = f"'{identifier}'" if quoted else identifier
        pieces.extend((literal, sentinel))
        output_length += len(literal)
        sites.append(
            InterpolationSite(
                sentinel=sentinel,
                neutralized_start=output_length,
                neutralized_end=output_length + len(sentinel),
                original_start=start,
                original_end=end,
                original_text=body[start:end],
            )
        )
        output_length += len(sentinel)
        copied_to = end
    pieces.append(body[copied_to:])
    return "".join(pieces), tuple(sites)


def neutralize_interpolation(*, body: str) -> tuple[str, tuple[InterpolationSite, ...]]:
    """Replace every interpolation site with a unique sentinel identifier."""

    if not _contains_interpolation_candidate(body=body):
        return body, ()
    sites: list[InterpolationSite] = []
    pieces: list[str] = []
    neutralized_length: int = 0
    copied_to: int = 0
    match: re.Match[str]
    for match in _INTERPOLATION_SCAN_PATTERN.finditer(body):
        if match.group("site") is None or match.start() < copied_to:
            continue
        site_start: int = match.start()
        site_end: int | None = _interpolation_site_end(body=body, start=site_start)
        if site_end is None:
            continue
        literal: str = body[copied_to:site_start]
        sentinel: str = SENTINEL_TEMPLATE.format(index=len(sites))
        pieces.append(literal)
        pieces.append(sentinel)
        neutralized_length += len(literal)
        sites.append(
            InterpolationSite(
                sentinel=sentinel,
                neutralized_start=neutralized_length,
                neutralized_end=neutralized_length + len(sentinel),
                original_start=site_start,
                original_end=site_end,
                original_text=body[site_start:site_end],
            )
        )
        neutralized_length += len(sentinel)
        copied_to = site_end
    pieces.append(body[copied_to:])
    return "".join(pieces), tuple(sites)


def _contains_interpolation_candidate(*, body: str) -> bool:
    return (
        MACRO_TOKEN in body
        or TEMPLATE_INTERPOLATION_START in body
        or any(name in body for name in _SQLBUILD_FUNCTION_NAMES)
    )


def restore_interpolation(*, fixed: str, sites: tuple[InterpolationSite, ...]) -> str:
    """Swap sentinels back to their original text, failing on any ambiguity."""

    restored: str = fixed
    site: InterpolationSite
    for site in sites:
        occurrences: int = restored.count(site.sentinel)
        if occurrences != EXPECTED_SENTINEL_OCCURRENCES:
            raise InterpolationRestorationError(
                f"formatted SQL contains {occurrences} occurrences of sentinel "
                f"'{site.sentinel}' standing in for '{site.original_text}'; expected "
                f"exactly {EXPECTED_SENTINEL_OCCURRENCES}"
            )
        restored = restored.replace(site.sentinel, site.original_text)
    return restored


def interpolation_text_at(*, body: str, start: int) -> str | None:
    """Return the interpolation token beginning at an offset, if there is one."""

    site_end: int | None = _interpolation_site_end(body=body, start=start)
    if site_end is None:
        return None
    return body[start:site_end]


def sentinel_spans(*, sites: tuple[InterpolationSite, ...]) -> tuple[ExpansionSpan, ...]:
    """Express sentinel substitutions as expansion spans for offset mapping."""

    spans: list[ExpansionSpan] = []
    site: InterpolationSite
    for site in sites:
        spans.append(
            ExpansionSpan(
                source_start=site.original_start,
                source_end=site.original_end,
                output_start=site.neutralized_start,
                output_end=site.neutralized_end,
            )
        )
    return tuple(spans)


def map_neutralized_offset(*, offset: int, sites: tuple[InterpolationSite, ...]) -> int:
    """Map an offset in neutralized text back onto the authored body."""

    mapped: int = offset
    site: InterpolationSite
    for site in sites:
        if offset < site.neutralized_start:
            break
        if offset < site.neutralized_end:
            return site.original_start
        mapped += (site.original_end - site.original_start) - (
            site.neutralized_end - site.neutralized_start
        )
    return mapped


def _interpolation_site_end(*, body: str, start: int) -> int | None:
    character: str = body[start]
    if character == MACRO_TOKEN:
        if body.startswith(SQL_INTERPOLATION_TOKEN, start):
            return _interpolation_name_end(body=body, start=start + len(SQL_INTERPOLATION_TOKEN))
        return _macro_site_end(body=body, start=start)
    if character == TEMPLATE_INTERPOLATION_START[0]:
        return _template_site_end(body=body, start=start)
    if character == IDENTIFIER_EXTRA_CHARACTER and body.startswith(_SQLBUILD_FUNCTION_NAMES, start):
        return _sqlbuild_function_site_end(body=body, start=start)
    return None


def _sqlbuild_function_site_end(*, body: str, start: int) -> int | None:
    name_end: int = _identifier_end(body=body, start=start)
    if name_end >= len(body) or body[name_end] != OPENING_PAREN_CHARACTER:
        return None
    call_end: int | None = _matching_paren_end(body=body, opening_index=name_end)
    if call_end is None or body[start:name_end] != _TABLE_FUNCTION_INTRINSIC_NAME:
        return call_end
    arguments_start: int = call_end
    while arguments_start < len(body) and body[arguments_start].isspace():
        arguments_start += 1
    if arguments_start < len(body) and body[arguments_start] == OPENING_PAREN_CHARACTER:
        return _matching_paren_end(body=body, opening_index=arguments_start)
    return call_end


def _template_site_end(*, body: str, start: int) -> int | None:
    end_index: int = body.find(
        TEMPLATE_INTERPOLATION_END, start + len(TEMPLATE_INTERPOLATION_START)
    )
    if end_index < 0:
        return None
    return end_index + len(TEMPLATE_INTERPOLATION_END)


def _macro_site_end(*, body: str, start: int) -> int | None:
    name_start: int = start + len(MACRO_TOKEN)
    if name_start >= len(body):
        return None
    if body[name_start] == SINGLE_QUOTE_CHARACTER:
        closing_index: int = body.find(SINGLE_QUOTE_CHARACTER, name_start + 1)
        if closing_index < 0:
            return None
        return closing_index + 1
    if not _is_identifier_start(character=body[name_start]):
        return None
    name_end: int = _identifier_end(body=body, start=name_start)
    if name_end >= len(body) or body[name_end] != OPENING_PAREN_CHARACTER:
        return name_end
    return _matching_paren_end(body=body, opening_index=name_end)


def _matching_paren_end(*, body: str, opening_index: int) -> int | None:
    depth: int = 0
    index: int = opening_index
    length: int = len(body)
    quote_character: str | None = None
    while index < length:
        if quote_character is None and body.startswith(_LINE_COMMENT_START, index):
            newline_index: int = body.find("\n", index + len(_LINE_COMMENT_START))
            index = length if newline_index < 0 else newline_index + 1
            continue
        if quote_character is None and body.startswith(_BLOCK_COMMENT_START, index):
            comment_end: int = body.find(_BLOCK_COMMENT_END, index + len(_BLOCK_COMMENT_START))
            index = length if comment_end < 0 else comment_end + len(_BLOCK_COMMENT_END)
            continue
        character: str = body[index]
        if quote_character is not None:
            if character == SQL_ESCAPE_CHARACTER and index + 1 < length:
                index += 2
                continue
            if character == quote_character:
                if index + 1 < length and body[index + 1] == quote_character:
                    index += 2
                    continue
                quote_character = None
            index += 1
            continue
        if character in SQL_QUOTE_CHARACTERS:
            quote_character = character
            index += 1
            continue
        if character == OPENING_PAREN_CHARACTER:
            depth += 1
        if character == CLOSING_PAREN_CHARACTER:
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return None


def _interpolation_name_end(*, body: str, start: int) -> int:
    index: int = start
    while index < len(body) and (
        body[index].isalnum() or body[index] in INTERPOLATION_NAME_EXTRA_CHARACTERS
    ):
        index += 1
    return index


def _identifier_end(*, body: str, start: int) -> int:
    index: int = start
    while index < len(body) and (
        body[index].isalnum() or body[index] == IDENTIFIER_EXTRA_CHARACTER
    ):
        index += 1
    return index


def _is_identifier_start(*, character: str) -> bool:
    return character.isalpha() or character == IDENTIFIER_EXTRA_CHARACTER
