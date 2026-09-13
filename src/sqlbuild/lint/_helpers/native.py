"""Native DSL header lint rules and formatting fixes."""

from __future__ import annotations

import re
import textwrap
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

from sqlbuild.compiler.discovery._helpers.sql.model_files import (
    parse_header_values,  # noqa: FFL102 - the compiler owns the canonical native header grammar
)
from sqlbuild.compiler.discovery.exceptions import ModelSqlParseError
from sqlbuild.lint.constants import (
    CLOSING_PAREN_CHARACTER,
    DESCRIPTION_HEADER_KINDS,
    DESCRIPTION_REQUIRED_HEADER_KINDS,
    HEADER_KIND_FUNCTION,
    HEADER_KIND_MODEL,
    IDENTIFIER_SEPARATOR_CHARACTER,
    RULE_DESCRIPTION_LENGTH,
    RULE_DESCRIPTION_PRESENT,
    RULE_HEADER_PARSE,
    RULE_HEADER_WHITESPACE,
    RULE_LEADING_COMMENT_DESCRIPTION,
    VIOLATION_SEVERITY_FAULT,
    VIOLATION_SEVERITY_WARNING,
)
from sqlbuild.lint.models import HeaderSpan, LintConfig, LintViolation

_QUOTE_CHARACTERS: frozenset[str] = frozenset({"'", '"'})
_ESCAPE_CHARACTER: str = "\\"
_NEWLINE: str = "\n"
_BLOCK_COMMENT_START: str = "/*"
_BLOCK_COMMENT_END: str = "*/"
_LINE_COMMENT_PREFIX: str = "--"
_DESCRIPTION_KEY: str = "description"
_DESCRIPTION_SENTINEL_PATH: str = "<lint>"
_HEADER_INDENT: str = "  "
_UNICODE_MAX_CODEPOINT: int = 0x10FFFF
_UNICODE_SURROGATE_START: int = 0xD800
_UNICODE_SURROGATE_END: int = 0xDFFF
_HEXADECIMAL_CHARACTERS: frozenset[str] = frozenset("0123456789abcdefABCDEF")


@dataclass(frozen=True)
class _RelocationOutcome:
    """Result of relocating a leading comment into the model description."""

    contents: str
    faults: tuple[LintViolation, ...]


def lint_native_headers(
    *,
    contents: str,
    file_path: Path,
    headers: tuple[HeaderSpan, ...],
    config: LintConfig,
) -> tuple[LintViolation, ...]:
    """Run all native header rules and return their violations."""

    violations: list[LintViolation] = []
    line_starts: tuple[int, ...] = _line_starts(contents)
    header: HeaderSpan
    for header in headers:
        violations.extend(
            _lint_header_values(
                contents=contents,
                file_path=file_path,
                header=header,
                config=config,
                line_starts=line_starts,
            )
        )
        violations.extend(
            _lint_header_whitespace(
                contents=contents,
                file_path=file_path,
                header=header,
                line_starts=line_starts,
            )
        )
    return tuple(violations)


def format_native_headers(
    *,
    contents: str,
    file_path: Path,
    config: LintConfig,
) -> tuple[str, tuple[LintViolation, ...]]:
    """Apply native header autofixes and return rewritten contents plus faults."""

    from sqlbuild.lint._helpers.headers import scan_headers

    headers: tuple[HeaderSpan, ...] = scan_headers(contents=contents)
    updated: str = _format_header_whitespace(contents=contents, headers=headers)
    relocation: _RelocationOutcome = _relocate_leading_comment(
        contents=updated,
        file_path=file_path,
        config=config,
        headers=headers,
    )
    relocated_headers: tuple[HeaderSpan, ...] = scan_headers(contents=relocation.contents)
    wrapped: str = _format_description_wrapping(
        contents=relocation.contents,
        headers=relocated_headers,
        config=config,
    )
    return wrapped, relocation.faults


def _lint_header_values(
    *,
    contents: str,
    file_path: Path,
    header: HeaderSpan,
    config: LintConfig,
    line_starts: tuple[int, ...],
) -> tuple[LintViolation, ...]:
    header_text: str = contents[header.start : header.end]
    try:
        values: dict[str, object] = _parse_header_values(kind=header.kind, header_text=header_text)
    except Exception as error:  # noqa: BLE001 - any parse failure is a lint fault
        position: tuple[int, int] = _offset_to_position(
            offset=header.start, line_starts=line_starts
        )
        return (
            LintViolation(
                file_path=file_path,
                line=position[0],
                column=position[1],
                code=RULE_HEADER_PARSE,
                message=f"{header.kind}() header could not be parsed: {error}",
                severity=VIOLATION_SEVERITY_FAULT,
                engine="sqlbuild",
                remediation=f"Correct the {header.kind}() header syntax.",
            ),
        )

    violations: list[LintViolation] = []
    description: object | None = values.get(_DESCRIPTION_KEY)
    span: tuple[int, int] | None = (
        _top_level_description_value_span(header_text=header_text)
        if header.kind in DESCRIPTION_HEADER_KINDS
        else None
    )
    effective_description: object | None = description
    if isinstance(description, str) and span is not None:
        value_start, value_end = span
        effective_description = _decode_quoted_description(
            value=header_text[value_start:value_end],
            quote=header_text[value_start - 1],
        )
    if header.kind in DESCRIPTION_REQUIRED_HEADER_KINDS and (
        not isinstance(effective_description, str) or not effective_description.strip()
    ):
        violations.append(
            _violation_for_header_start(
                contents=contents,
                file_path=file_path,
                header=header,
                code=RULE_DESCRIPTION_PRESENT,
                message=f"{header.kind}() header requires a description",
                remediation=f"Add a description to the {header.kind}() header.",
            )
        )
    if header.kind in DESCRIPTION_HEADER_KINDS and isinstance(effective_description, str):
        formatted_description: str = (
            _wrap_header_description(
                description=effective_description,
                header_text=header_text,
                span=span,
                line_width=config.line_width,
            )
            if span is not None
            else effective_description
        )
        if formatted_description.count("\n") + 1 > config.max_description_lines:
            violations.append(
                _violation_for_header_start(
                    contents=contents,
                    file_path=file_path,
                    header=header,
                    code=RULE_DESCRIPTION_LENGTH,
                    message=f"Description exceeds {config.max_description_lines} lines",
                    remediation=f"Shorten the description to {config.max_description_lines} lines.",
                )
            )
    return tuple(violations)


def _parse_header_values(*, kind: str, header_text: str) -> dict[str, object]:
    inner: str = _inner_header_text(header_text=header_text)
    return parse_header_values(
        header=inner,
        file_path=Path(_DESCRIPTION_SENTINEL_PATH),
        statement_name=kind,
    )


def external_identifiers_for_headers(
    *, contents: str, headers: tuple[HeaderSpan, ...]
) -> tuple[str, ...]:
    """Return SQL function argument names that are values rather than columns."""
    for header in headers:
        if header.kind != HEADER_KIND_FUNCTION:
            continue
        values: dict[str, object] = _parse_header_values(
            kind=header.kind,
            header_text=contents[header.start : header.end],
        )
        arguments: object = values.get("arguments")
        if isinstance(arguments, dict):
            return tuple(sorted(str(name).lower() for name in arguments))
    return ()


def _lint_header_whitespace(
    *,
    contents: str,
    file_path: Path,
    header: HeaderSpan,
    line_starts: tuple[int, ...],
) -> tuple[LintViolation, ...]:
    header_text: str = contents[header.start : header.end]
    if not any(line != line.rstrip() for line in _split_outside_quotes(text=header_text)):
        return ()
    position: tuple[int, int] = _offset_to_position(offset=header.start, line_starts=line_starts)
    return (
        LintViolation(
            file_path=file_path,
            line=position[0],
            column=position[1],
            code=RULE_HEADER_WHITESPACE,
            message=f"{header.kind}() header contains trailing whitespace",
            severity=VIOLATION_SEVERITY_WARNING,
            engine="sqlbuild",
            remediation="Run sqb format to remove trailing header whitespace.",
        ),
    )


def _format_header_whitespace(*, contents: str, headers: tuple[HeaderSpan, ...]) -> str:
    pieces: list[str] = []
    cursor: int = 0
    header: HeaderSpan
    for header in headers:
        pieces.append(contents[cursor : header.start])
        pieces.append(
            "\n".join(
                line.rstrip()
                for line in _split_outside_quotes(text=contents[header.start : header.end])
            )
        )
        cursor = header.end
    pieces.append(contents[cursor:])
    return "".join(pieces)


def _format_description_wrapping(
    *, contents: str, headers: tuple[HeaderSpan, ...], config: LintConfig
) -> str:
    updated: str = contents
    for header in reversed(headers):
        if header.kind not in DESCRIPTION_HEADER_KINDS:
            continue
        header_text: str = updated[header.start : header.end]
        span: tuple[int, int] | None = _top_level_description_value_span(header_text=header_text)
        if span is None:
            continue
        try:
            description: object | None = _parse_header_values(
                kind=header.kind,
                header_text=header_text,
            ).get(_DESCRIPTION_KEY)
        except ModelSqlParseError:
            continue
        if not isinstance(description, str):
            continue
        value_start, value_end = span
        quote: str = header_text[value_start - 1]
        wrapped: str = _wrap_header_description(
            description=_decode_quoted_description(
                value=header_text[value_start:value_end], quote=quote
            ),
            header_text=header_text,
            span=span,
            line_width=config.line_width,
        )
        escaped: str = _escape_quoted_value(value=wrapped, quote=quote)
        rewritten_header: str = header_text[:value_start] + escaped + header_text[value_end:]
        updated = updated[: header.start] + rewritten_header + updated[header.end :]
    return updated


def _wrap_header_description(
    *, description: str, header_text: str, span: tuple[int, int], line_width: int
) -> str:
    value_start, value_end = span
    line_start: int = header_text.rfind(_NEWLINE, 0, value_start) + 1
    line_end: int = header_text.find(_NEWLINE, value_end)
    if line_end < 0:
        line_end = len(header_text)
    closing_suffix_width: int = len(header_text[value_end:line_end].rstrip())
    wrapped_line_width: int = max(1, line_width - closing_suffix_width)
    first_line_width: int = max(
        1,
        line_width - (value_start - line_start) - closing_suffix_width,
    )
    return _wrap_description(
        description=description,
        first_line_width=first_line_width,
        line_width=wrapped_line_width,
    )


def _top_level_description_value_span(*, header_text: str) -> tuple[int, int] | None:
    delimiters: list[str] = []
    closing_delimiters: dict[str, str] = {"(": ")", "[": "]", "{": "}"}
    index: int = 0
    while index < len(header_text):
        character: str = header_text[index]
        if character in _QUOTE_CHARACTERS:
            index = _quoted_value_end(text=header_text, start=index)
            continue
        if character in closing_delimiters:
            delimiters.append(closing_delimiters[character])
            index += 1
            continue
        if delimiters and character == delimiters[-1]:
            delimiters.pop()
            index += 1
            continue
        if delimiters == [CLOSING_PAREN_CHARACTER] and (
            character.isalpha() or character == IDENTIFIER_SEPARATOR_CHARACTER
        ):
            word_end: int = index + 1
            while word_end < len(header_text) and (
                header_text[word_end].isalnum()
                or header_text[word_end] == IDENTIFIER_SEPARATOR_CHARACTER
            ):
                word_end += 1
            if header_text[index:word_end].lower() == _DESCRIPTION_KEY:
                quote_start: int = word_end
                while quote_start < len(header_text) and header_text[quote_start].isspace():
                    quote_start += 1
                if quote_start < len(header_text) and header_text[quote_start] in _QUOTE_CHARACTERS:
                    quote_end: int = _quoted_value_end(text=header_text, start=quote_start)
                    return quote_start + 1, quote_end - 1
            index = word_end
            continue
        index += 1
    return None


def _quoted_value_end(*, text: str, start: int) -> int:
    quote: str = text[start]
    index: int = start + 1
    while index < len(text):
        if text[index] == _ESCAPE_CHARACTER and index + 1 < len(text):
            index += 2
            continue
        if text[index] == quote:
            return index + 1
        index += 1
    return len(text)


def _wrap_description(*, description: str, first_line_width: int, line_width: int) -> str:
    normalized: str = description.replace("\r\n", _NEWLINE).strip()
    paragraphs: list[str] = re.split(r"\n\s*\n", normalized)
    wrapped_paragraphs: list[str] = []
    for paragraph_index, paragraph in enumerate(paragraphs):
        prose: str = " ".join(paragraph.split())
        if not prose:
            continue
        available_first_width: int = first_line_width if paragraph_index == 0 else line_width
        synthetic_indent: str = " " * max(0, line_width - available_first_width)
        wrapper: textwrap.TextWrapper = textwrap.TextWrapper(
            width=line_width,
            initial_indent=synthetic_indent,
            subsequent_indent="",
            break_long_words=False,
            break_on_hyphens=False,
        )
        lines: list[str] = wrapper.wrap(prose)
        if lines and synthetic_indent:
            lines[0] = lines[0][len(synthetic_indent) :]
        wrapped_paragraphs.append(_NEWLINE.join(lines))
    return f"{_NEWLINE}{_NEWLINE}".join(wrapped_paragraphs)


def _escape_quoted_value(*, value: str, quote: str) -> str:
    return value.replace(_ESCAPE_CHARACTER, _ESCAPE_CHARACTER * 2).replace(
        quote, _ESCAPE_CHARACTER + quote
    )


def _decode_quoted_description(*, value: str, quote: str) -> str:
    decoded: list[str] = []
    escape_values: dict[str, str] = {
        "b": "\b",
        "f": "\f",
        "n": _NEWLINE,
        "r": "\r",
        "t": "\t",
    }
    index: int = 0
    while index < len(value):
        character: str = value[index]
        if character != _ESCAPE_CHARACTER or index + 1 >= len(value):
            decoded.append(character)
            index += 1
            continue
        escaped: str = value[index + 1]
        if escaped in {_ESCAPE_CHARACTER, quote}:
            decoded.append(escaped)
            index += 2
            continue
        if escaped in escape_values:
            decoded.append(escape_values[escaped])
            index += 2
            continue
        unicode_width: int = {"u": 4, "U": 8}.get(escaped, 0)
        digits: str = value[index + 2 : index + 2 + unicode_width]
        if (
            unicode_width
            and len(digits) == unicode_width
            and all(character in _HEXADECIMAL_CHARACTERS for character in digits)
        ):
            try:
                codepoint: int = int(digits, 16)
            except ValueError:
                pass
            else:
                if codepoint <= _UNICODE_MAX_CODEPOINT and not (
                    _UNICODE_SURROGATE_START <= codepoint <= _UNICODE_SURROGATE_END
                ):
                    decoded.append(chr(codepoint))
                    index += unicode_width + 2
                    continue
        decoded.extend((_ESCAPE_CHARACTER, escaped))
        index += 2
    return "".join(decoded)


def _relocate_leading_comment(
    *, contents: str, file_path: Path, config: LintConfig, headers: tuple[HeaderSpan, ...]
) -> _RelocationOutcome:
    if not headers or headers[0].kind != HEADER_KIND_MODEL:
        return _RelocationOutcome(contents=contents, faults=())
    header: HeaderSpan = headers[0]
    comment_text: str | None = _leading_comment_text(preamble=contents[: header.start])
    if comment_text is None:
        return _RelocationOutcome(contents=contents, faults=())

    header_text: str = contents[header.start : header.end]
    try:
        values: dict[str, object] = _parse_header_values(kind=header.kind, header_text=header_text)
    except Exception:  # noqa: BLE001 - leave unparseable headers to the parse rule
        return _RelocationOutcome(contents=contents, faults=())
    if isinstance(values.get(_DESCRIPTION_KEY), str):
        return _RelocationOutcome(contents=contents, faults=())

    description_prefix_width: int = len(_HEADER_INDENT) + len(_DESCRIPTION_KEY) + 2
    closing_description_syntax_width: int = len('",')
    relocated_description: str = _wrap_description(
        description=comment_text,
        first_line_width=max(
            1,
            config.line_width - description_prefix_width - closing_description_syntax_width,
        ),
        line_width=max(1, config.line_width - closing_description_syntax_width),
    )
    faults: list[LintViolation] = []
    if relocated_description.count("\n") + 1 > config.max_description_lines:
        position: tuple[int, int] = _offset_to_position(
            offset=header.start, line_starts=_line_starts(contents)
        )
        faults.append(
            LintViolation(
                file_path=file_path,
                line=position[0],
                column=position[1],
                code=RULE_LEADING_COMMENT_DESCRIPTION,
                message=(f"Relocated leading comment exceeds {config.max_description_lines} lines"),
                severity=VIOLATION_SEVERITY_FAULT,
                engine="sqlbuild",
                remediation=(
                    f"Shorten the relocated description to {config.max_description_lines} lines."
                ),
            )
        )

    escaped_description: str = _escape_description(relocated_description)
    insertion: str = f'\n{_HEADER_INDENT}{_DESCRIPTION_KEY} "{escaped_description}",'
    updated_header: str = _insert_after_open_paren(header_text=header_text, insertion=insertion)
    return _RelocationOutcome(
        contents=updated_header + contents[header.end :], faults=tuple(faults)
    )


def _leading_comment_text(*, preamble: str) -> str | None:
    stripped: str = preamble.strip()
    if not stripped:
        return None
    if stripped.startswith(_BLOCK_COMMENT_START):
        end_index: int = stripped.find(_BLOCK_COMMENT_END, len(_BLOCK_COMMENT_START))
        if end_index < 0:
            return None
        return stripped[len(_BLOCK_COMMENT_START) : end_index]
    lines: list[str] = []
    collecting: bool = False
    raw_line: str
    for raw_line in preamble.splitlines():
        candidate: str = raw_line.strip()
        if candidate.startswith(_LINE_COMMENT_PREFIX):
            lines.append(candidate[len(_LINE_COMMENT_PREFIX) :].lstrip())
            collecting = True
            continue
        if collecting:
            break
        if candidate:
            return None
    if not lines or not collecting:
        return None
    return "\n".join(lines)


def _escape_description(description: str) -> str:
    return description.replace("\\", "\\\\").replace('"', '\\"').replace("\r\n", "\n")


def _insert_after_open_paren(*, header_text: str, insertion: str) -> str:
    open_index: int = header_text.find("(")
    if open_index < 0:
        return header_text
    return header_text[: open_index + 1] + insertion + header_text[open_index + 1 :]


def _split_outside_quotes(*, text: str) -> list[str]:
    lines: list[str] = []
    current: list[str] = []
    in_quote: str | None = None
    index: int = 0
    length: int = len(text)
    while index < length:
        character: str = text[index]
        if in_quote is not None:
            current.append(character)
            if character == _ESCAPE_CHARACTER and index + 1 < length:
                current.append(text[index + 1])
                index += 2
                continue
            if character == in_quote:
                in_quote = None
            index += 1
            continue
        if character in _QUOTE_CHARACTERS:
            in_quote = character
            current.append(character)
            index += 1
            continue
        if character == _NEWLINE:
            lines.append("".join(current))
            current = []
            index += 1
            continue
        current.append(character)
        index += 1
    lines.append("".join(current))
    return lines


def _violation_for_header_start(
    *,
    contents: str,
    file_path: Path,
    header: HeaderSpan,
    code: str,
    message: str,
    remediation: str,
) -> LintViolation:
    position: tuple[int, int] = _offset_to_position(
        offset=header.start, line_starts=_line_starts(contents)
    )
    return LintViolation(
        file_path=file_path,
        line=position[0],
        column=position[1],
        code=code,
        message=message,
        severity=VIOLATION_SEVERITY_FAULT,
        engine="sqlbuild",
        remediation=remediation,
    )


def _line_starts(contents: str) -> tuple[int, ...]:
    starts: list[int] = [0]
    index: int = contents.find("\n")
    while index >= 0:
        starts.append(index + 1)
        index = contents.find("\n", index + 1)
    return tuple(starts)


def _offset_to_position(*, offset: int, line_starts: tuple[int, ...]) -> tuple[int, int]:
    line_index: int = bisect_right(line_starts, offset) - 1
    return line_index + 1, offset - line_starts[line_index] + 1


def _inner_header_text(*, header_text: str) -> str:
    open_index: int = header_text.find("(")
    close_index: int = header_text.rfind(")")
    if open_index < 0 or close_index <= open_index:
        return ""
    return header_text[open_index + 1 : close_index]
