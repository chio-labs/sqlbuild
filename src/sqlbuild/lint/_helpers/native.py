"""Native DSL header lint rules and formatting fixes."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

from sqlbuild.compiler.discovery._helpers.sql.model_files import (
    parse_header_values,  # noqa: FFL102 - the compiler owns the canonical native header grammar
)
from sqlbuild.lint.constants import (
    DESCRIPTION_HEADER_KINDS,
    DESCRIPTION_REQUIRED_HEADER_KINDS,
    HEADER_KIND_MODEL,
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
    return relocation.contents, relocation.faults


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
    if header.kind in DESCRIPTION_REQUIRED_HEADER_KINDS and not isinstance(description, str):
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
    if header.kind in DESCRIPTION_HEADER_KINDS and isinstance(description, str):
        if description.count("\n") + 1 > config.max_description_lines:
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

    relocated_description: str = comment_text.strip("\n").strip()
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
