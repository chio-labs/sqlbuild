"""Neutralize SQLBuild interpolation for native SQL analysis and formatting."""

from __future__ import annotations

import re
from functools import cache

import sqlbuild._native as _native
from sqlbuild.compiler.compile.constants import (
    MACRO_TOKEN,
    SQL_ARGUMENT_QUOTED_PARAMETER_PATTERN,
    SQL_ARGUMENT_RAW_PARAMETER_PATTERN,
    SQL_INTERPOLATION_TOKEN,
)
from sqlbuild.compiler.compile.models import ExpansionSpan
from sqlbuild.lint.constants import (
    BACKTICK_CHARACTER,
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

_SQLBUILD_REFERENCE_FUNCTION_NAMES: tuple[str, ...] = (
    "__dbt_ref",
    "__table_fn",
    "__source",
    "__seed",
    "__udf",
    "__ref",
)
_SQLBUILD_FUNCTION_NAMES: tuple[str, ...] = (
    "__cursor_start",
    "__cursor_end",
    "__empty_fixture",
    *_SQLBUILD_REFERENCE_FUNCTION_NAMES,
)
_AUDIT_PARAMETER_SENTINEL_TEMPLATE: str = "__sqlbuild_audit_parameter_{index}__"
_CONTEXT_SENTINEL_TEMPLATE: str = "__sqlbuild_context_parameter_{index}__"
_LINE_COMMENT_START: str = "--"
_BLOCK_COMMENT_START: str = "/*"
_BLOCK_COMMENT_END: str = "*/"
_NON_CODE_SCAN_PATTERN: str = (
    r"--[^\n]*(?:\n|\Z)"
    r"|/\*[\s\S]*?(?:\*/|\Z)"
    r"|'(?:\\.|''|[^'\\])*(?:'|\Z)"
    r'|"(?:\\.|""|[^"\\])*(?:"|\Z)'
)
_BACKTICK_SCAN_PATTERN: str = r"|`(?:``|[^`])*(?:`|\Z)"


@cache
def _interpolation_scan_pattern(
    *, backtick_identifiers: bool, for_formatting: bool
) -> re.Pattern[str]:
    """Keep lint fallback lexical policy identical to the native ASCII fast path."""

    names: tuple[str, ...] = (
        _SQLBUILD_FUNCTION_NAMES if for_formatting else _SQLBUILD_REFERENCE_FUNCTION_NAMES
    )
    functions: str = "|".join(re.escape(name) for name in sorted(names))
    whitespace: str = r"\s*" if for_formatting else ""
    sites: str = rf"|(?P<site>@@|\$\{{|@|(?:{functions}){whitespace}\()"
    backticks: str = _BACKTICK_SCAN_PATTERN if backtick_identifiers else ""
    flags: re.RegexFlag = re.IGNORECASE if for_formatting else re.NOFLAG
    return re.compile(_NON_CODE_SCAN_PATTERN + backticks + sites, flags)


@cache
def _backtick_identifiers(dialect: str) -> bool:
    """Return whether lint treats backticks as identifier quotes, matching the native lexer."""

    return _native.lint_backtick_identifiers(dialect)


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
        end: int = _interpolation_name_end(body=body, start=start + len(SQL_INTERPOLATION_TOKEN))
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


def neutralize_interpolation(
    *, body: str, dialect: str, for_formatting: bool = False
) -> tuple[str, tuple[InterpolationSite, ...]]:
    """Neutralize references for lint, or protect every intrinsic spelling for formatting."""

    if not _contains_interpolation_candidate(body=body):
        return body, ()
    backtick_identifiers: bool = _backtick_identifiers(dialect)
    scan_pattern: re.Pattern[str] = _interpolation_scan_pattern(
        backtick_identifiers=backtick_identifiers, for_formatting=for_formatting
    )
    sites: list[InterpolationSite] = []
    pieces: list[str] = []
    neutralized_length: int = 0
    copied_to: int = 0
    match: re.Match[str]
    for match in scan_pattern.finditer(body):
        if match.group("site") is None or match.start() < copied_to:
            continue
        site_start: int = match.start()
        site_end: int | None = _interpolation_site_end(
            body=body, start=site_start, backtick_identifiers=backtick_identifiers
        )
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
        or any(name in body.lower() for name in _SQLBUILD_FUNCTION_NAMES)
    )


def restore_interpolation(*, fixed: str, sites: tuple[InterpolationSite, ...]) -> str:
    """Swap sentinels back to their original text, failing on any ambiguity."""

    restored: str = fixed
    site: InterpolationSite
    for site in sites:
        pattern: re.Pattern[str] = re.compile(re.escape(site.sentinel), re.IGNORECASE)
        occurrences: int = len(tuple(pattern.finditer(restored)))
        if occurrences != EXPECTED_SENTINEL_OCCURRENCES:
            raise InterpolationRestorationError(
                f"formatted SQL contains {occurrences} occurrences of sentinel "
                f"'{site.sentinel}' standing in for '{site.original_text}'; expected "
                f"exactly {EXPECTED_SENTINEL_OCCURRENCES}"
            )
        restored = pattern.sub(
            lambda _match, original_text=site.original_text: original_text,
            restored,
        )
    return restored


def interpolation_text_at(*, body: str, start: int, dialect: str) -> str | None:
    """Return the interpolation token beginning at an offset, if there is one."""

    site_end: int | None = _interpolation_site_end(
        body=body, start=start, backtick_identifiers=_backtick_identifiers(dialect)
    )
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


def _interpolation_site_end(*, body: str, start: int, backtick_identifiers: bool) -> int | None:
    character: str = body[start]
    if character == MACRO_TOKEN:
        if body.startswith(SQL_INTERPOLATION_TOKEN, start):
            return _interpolation_name_end(body=body, start=start + len(SQL_INTERPOLATION_TOKEN))
        return _macro_site_end(body=body, start=start, backtick_identifiers=backtick_identifiers)
    if character == TEMPLATE_INTERPOLATION_START[0]:
        return _template_site_end(body=body, start=start)
    if (
        character == IDENTIFIER_EXTRA_CHARACTER
        and body[start : _identifier_end(body=body, start=start)].lower()
        in _SQLBUILD_FUNCTION_NAMES
    ):
        return _sqlbuild_function_site_end(
            body=body, start=start, backtick_identifiers=backtick_identifiers
        )
    return None


def _sqlbuild_function_site_end(*, body: str, start: int, backtick_identifiers: bool) -> int | None:
    name_end: int = _identifier_end(body=body, start=start)
    while name_end < len(body) and body[name_end].isspace():
        name_end += 1
    if name_end >= len(body) or body[name_end] != OPENING_PAREN_CHARACTER:
        return None
    call_end: int | None = _matching_paren_end(
        body=body, opening_index=name_end, backtick_identifiers=backtick_identifiers
    )
    return call_end


def _template_site_end(*, body: str, start: int) -> int | None:
    end_index: int = body.find(
        TEMPLATE_INTERPOLATION_END, start + len(TEMPLATE_INTERPOLATION_START)
    )
    if end_index < 0:
        return None
    return end_index + len(TEMPLATE_INTERPOLATION_END)


def _macro_site_end(*, body: str, start: int, backtick_identifiers: bool) -> int | None:
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
    return _matching_paren_end(
        body=body, opening_index=name_end, backtick_identifiers=backtick_identifiers
    )


def _matching_paren_end(*, body: str, opening_index: int, backtick_identifiers: bool) -> int | None:
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
            if (
                character == SQL_ESCAPE_CHARACTER
                and quote_character in SQL_QUOTE_CHARACTERS
                and index + 1 < length
            ):
                index += 2
                continue
            if character == quote_character:
                if index + 1 < length and body[index + 1] == quote_character:
                    index += 2
                    continue
                quote_character = None
            index += 1
            continue
        if character in SQL_QUOTE_CHARACTERS or (
            backtick_identifiers and character == BACKTICK_CHARACTER
        ):
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
