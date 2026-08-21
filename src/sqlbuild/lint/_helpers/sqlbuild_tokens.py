"""Neutralize sqlbuild interpolation so sqruff can parse authored SQL bodies."""

from __future__ import annotations

from sqlbuild.compiler.compile.constants import MACRO_TOKEN, SQL_INTERPOLATION_TOKEN
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


def neutralize_interpolation(*, body: str) -> tuple[str, tuple[InterpolationSite, ...]]:
    """Replace every interpolation site with a unique sentinel identifier."""

    sites: list[InterpolationSite] = []
    pieces: list[str] = []
    neutralized_length: int = 0
    copied_to: int = 0
    index: int = 0
    length: int = len(body)
    quote_character: str | None = None
    while index < length:
        character: str = body[index]
        if quote_character is not None:
            if character == SQL_ESCAPE_CHARACTER and index + 1 < length:
                index += 2
                continue
            if character == quote_character:
                quote_character = None
            index += 1
            continue
        if character in SQL_QUOTE_CHARACTERS:
            quote_character = character
            index += 1
            continue
        site_end: int | None = _interpolation_site_end(body=body, start=index)
        if site_end is None:
            index += 1
            continue
        literal: str = body[copied_to:index]
        sentinel: str = SENTINEL_TEMPLATE.format(index=len(sites))
        pieces.append(literal)
        pieces.append(sentinel)
        neutralized_length += len(literal)
        sites.append(
            InterpolationSite(
                sentinel=sentinel,
                neutralized_start=neutralized_length,
                neutralized_end=neutralized_length + len(sentinel),
                original_start=index,
                original_end=site_end,
                original_text=body[index:site_end],
            )
        )
        neutralized_length += len(sentinel)
        index = site_end
        copied_to = site_end
    pieces.append(body[copied_to:])
    return "".join(pieces), tuple(sites)


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
    if body.startswith(SQL_INTERPOLATION_TOKEN, start):
        return _interpolation_name_end(body=body, start=start + len(SQL_INTERPOLATION_TOKEN))
    if body.startswith(TEMPLATE_INTERPOLATION_START, start):
        return _template_site_end(body=body, start=start)
    if body.startswith(MACRO_TOKEN, start):
        return _macro_site_end(body=body, start=start)
    return None


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
        character: str = body[index]
        if quote_character is not None:
            if character == SQL_ESCAPE_CHARACTER and index + 1 < length:
                index += 2
                continue
            if character == quote_character:
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
