"""Python boundary for SQLBuild-owned Polyglot-backed native SQL lint."""

from __future__ import annotations

import json
import os
import re
from bisect import bisect_right
from concurrent.futures import ThreadPoolExecutor
from itertools import chain
from pathlib import Path
from typing import Any, cast

import sqlbuild._native as _native
from sqlbuild.compiler.compile.constants import (
    ASSERT_TEST_CTE_PREFIX,
    DBT_REF_TEST_CTE_PREFIX,
    EXPECTED_TEST_CTE_PREFIX,
    MACRO_TEST_CTE_PREFIX,
    REF_TEST_CTE_PREFIX,
    SEED_TEST_CTE_PREFIX,
    SOURCE_TEST_CTE_PREFIX,
)
from sqlbuild.compiler.compile.main.map_expanded_offset import map_expanded_offset
from sqlbuild.compiler.compile.models import MappedOffset
from sqlbuild.lint._helpers.sqlbuild_tokens import interpolation_text_at
from sqlbuild.lint.constants import (
    GENERATED_SQL_MESSAGE_SUFFIX,
    GENERATED_SQL_MESSAGE_TEMPLATE,
    LINT_ENGINE_NATIVE,
    VIOLATION_SEVERITY_FAULT,
    VIOLATION_SEVERITY_WARNING,
)
from sqlbuild.lint.exceptions import NativeLintError
from sqlbuild.lint.models import LintBody, LintConfig, LintEdit, LintViolation

_NATIVE_LINT_API_VERSION: int = 1
_MAX_NATIVE_LINT_WORKERS: int = 8
_NEWLINE_CHARACTER: str = "\n"
_UNUSED_CTE_CODE: str = "SQBL005"
_PARSE_ERROR_POSITION_PATTERN: re.Pattern[str] = re.compile(
    r"^Parse error at line (?P<line>\d+), column (?P<column>\d+):"
)
_SQLBUILD_HARNESS_CTE_PREFIXES: tuple[str, ...] = (
    EXPECTED_TEST_CTE_PREFIX,
    ASSERT_TEST_CTE_PREFIX,
    REF_TEST_CTE_PREFIX,
    SOURCE_TEST_CTE_PREFIX,
    SEED_TEST_CTE_PREFIX,
    DBT_REF_TEST_CTE_PREFIX,
    MACRO_TEST_CTE_PREFIX,
)
type _NativeCacheKey = tuple[str, str, tuple[str, ...] | None, tuple[str, ...]]
type _NativeResult = dict[str, Any] | NativeLintError


def run_native_sql_lint(
    *,
    bodies: tuple[LintBody, ...],
    contents_by_path: dict[Path, str],
    config: LintConfig,
) -> dict[Path, tuple[LintViolation, ...]]:
    """Lint expanded bodies in Rust and map diagnostics to authored source."""

    violations_by_file: dict[Path, list[LintViolation]] = {}
    requests: dict[_NativeCacheKey, dict[str, object]] = {}
    for body in bodies:
        cache_key: _NativeCacheKey = _native_cache_key(body=body, config=config)
        if cache_key in requests:
            continue
        payload: dict[str, object] = {
            "version": _NATIVE_LINT_API_VERSION,
            "sql": body.lint_text,
            "dialect": config.dialect,
        }
        if config.enabled_native_rules is not None:
            payload["enabled_rules"] = list(config.enabled_native_rules)
        if config.ignored_native_rules:
            payload["ignored_rules"] = list(config.ignored_native_rules)
        requests[cache_key] = payload
    response_cache: dict[_NativeCacheKey, _NativeResult] = _native_responses(requests=requests)

    for body in bodies:
        response: _NativeResult = response_cache[_native_cache_key(body=body, config=config)]
        if isinstance(response, NativeLintError):
            parse_violation: LintViolation | None = _parse_failure_violation(
                error=response,
                body=body,
                contents=contents_by_path[body.file_path],
            )
            if parse_violation is None:
                raise response
            violations_by_file.setdefault(body.file_path, []).append(parse_violation)
            continue
        raw_diagnostics: object = response.get("diagnostics")
        if not isinstance(raw_diagnostics, list):
            raise NativeLintError("native lint response is missing a diagnostics list")
        for raw_diagnostic in raw_diagnostics:
            violation: LintViolation | None = _authored_violation(
                raw_diagnostic=raw_diagnostic,
                body=body,
                contents=contents_by_path[body.file_path],
            )
            if violation is not None:
                violations_by_file.setdefault(body.file_path, []).append(violation)
    return {path: tuple(entries) for path, entries in violations_by_file.items()}


def _native_cache_key(*, body: LintBody, config: LintConfig) -> _NativeCacheKey:
    return (
        body.lint_text,
        config.dialect,
        config.enabled_native_rules,
        config.ignored_native_rules,
    )


def _native_responses(
    *, requests: dict[_NativeCacheKey, dict[str, object]]
) -> dict[_NativeCacheKey, _NativeResult]:
    """Analyze unique SQL bodies concurrently while preserving request order."""

    keys: tuple[_NativeCacheKey, ...] = tuple(requests)
    payloads: tuple[dict[str, object], ...] = tuple(requests.values())
    worker_count: int = min(
        len(payloads),
        _MAX_NATIVE_LINT_WORKERS,
        os.cpu_count() or 1,
    )
    if worker_count <= 1:
        results: tuple[_NativeResult, ...] = tuple(
            _native_response_or_error(payload=payload) for payload in payloads
        )
    else:
        chunk_size: int = (len(payloads) + worker_count - 1) // worker_count
        chunks: tuple[tuple[dict[str, object], ...], ...] = tuple(
            payloads[start : start + chunk_size] for start in range(0, len(payloads), chunk_size)
        )
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            results = tuple(chain.from_iterable(executor.map(_native_response_chunk, chunks)))
    return dict(zip(keys, results, strict=True))


def _native_response_or_error(payload: dict[str, object]) -> _NativeResult:
    try:
        return _native_response(payload=payload)
    except NativeLintError as error:
        return error


def _native_response_chunk(
    payloads: tuple[dict[str, object], ...],
) -> tuple[_NativeResult, ...]:
    return tuple(_native_response_or_error(payload) for payload in payloads)


def _parse_failure_violation(
    *, error: NativeLintError, body: LintBody, contents: str
) -> LintViolation | None:
    """Convert a per-body native parse rejection into an authored project fault."""

    match: re.Match[str] | None = _PARSE_ERROR_POSITION_PATTERN.match(error.message)
    if match is None:
        return None
    expanded_line: int = int(match.group("line"))
    expanded_column: int = int(match.group("column"))
    expanded_lines: list[str] = body.lint_text.splitlines(keepends=True)
    expanded_offset: int = 0
    if 1 <= expanded_line <= len(expanded_lines):
        expanded_offset = sum(len(line) for line in expanded_lines[: expanded_line - 1])
        expanded_offset += min(expanded_column - 1, len(expanded_lines[expanded_line - 1]))
    mapped: MappedOffset = map_expanded_offset(offset=expanded_offset, passes=body.passes)
    absolute_offset: int = body.body_start + mapped.offset
    line, column = _offset_position(offset=absolute_offset, line_starts=_line_starts(contents))
    return LintViolation(
        file_path=body.file_path,
        line=line,
        column=column,
        code=error.code,
        message=f"Native SQL parser could not analyze this body: {error.message}",
        severity=VIOLATION_SEVERITY_FAULT,
        engine=LINT_ENGINE_NATIVE,
        remediation="Use SQL syntax supported by the native parser or report the parser gap.",
    )


def _native_response(*, payload: dict[str, object]) -> dict[str, Any]:
    try:
        decoded: object = json.loads(
            _native.lint_sql_json(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        )
    except (TypeError, ValueError) as error:
        raise NativeLintError(str(error)) from error
    if not isinstance(decoded, dict):
        raise NativeLintError("native lint engine returned a non-object response")
    if decoded.get("version") != _NATIVE_LINT_API_VERSION:
        raise NativeLintError("native lint engine returned an unsupported response version")
    return {str(key): value for key, value in decoded.items()}


def _authored_violation(
    *, raw_diagnostic: object, body: LintBody, contents: str
) -> LintViolation | None:
    if not isinstance(raw_diagnostic, dict):
        raise NativeLintError("native lint diagnostic must be an object")
    diagnostic: dict[str, object] = cast("dict[str, object]", raw_diagnostic)
    code: object = diagnostic.get("code")
    message: object = diagnostic.get("message")
    remediation: object = diagnostic.get("remediation")
    start: object = diagnostic.get("start")
    end: object = diagnostic.get("end")
    raw_fix: object = diagnostic.get("fix")
    raw_fix_unavailable_reason: object = diagnostic.get("fix_unavailable_reason")
    if (
        not isinstance(code, str)
        or not isinstance(message, str)
        or not isinstance(remediation, str)
        or not isinstance(start, int)
        or isinstance(start, bool)
        or not isinstance(end, int)
        or isinstance(end, bool)
        or start < 0
        or end < start
        or end > len(body.lint_text)
    ):
        raise NativeLintError("native lint diagnostic has invalid code, message, or source span")
    if raw_fix_unavailable_reason is not None and not isinstance(raw_fix_unavailable_reason, str):
        raise NativeLintError("native lint diagnostic has an invalid fix refusal reason")
    mapped: MappedOffset = map_expanded_offset(offset=start, passes=body.passes)
    absolute_offset: int = body.body_start + mapped.offset
    if code == _UNUSED_CTE_CODE and contents.startswith(
        _SQLBUILD_HARNESS_CTE_PREFIXES, absolute_offset
    ):
        return None
    starts: tuple[int, ...] = _line_starts(contents)
    line, column = _offset_position(offset=absolute_offset, line_starts=starts)
    end_position: tuple[int, int] | None = _authored_end_position(
        start=start,
        end=end,
        mapped_start=mapped,
        absolute_start=absolute_offset,
        body=body,
        contents=contents,
        line_starts=starts,
    )
    fix: LintEdit | None = _authored_fix(
        raw_fix=raw_fix,
        code=code,
        body=body,
    )
    fix_unavailable_reason: str | None = raw_fix_unavailable_reason
    if raw_fix is not None and fix is None:
        fix_unavailable_reason = "fix overlaps generated SQL or a non-contiguous authored region"
    return LintViolation(
        file_path=body.file_path,
        line=line,
        column=column,
        code=code,
        message=_violation_message(
            message=message,
            mapped=mapped,
            contents=contents,
            absolute_offset=absolute_offset,
        ),
        severity=VIOLATION_SEVERITY_WARNING,
        engine=LINT_ENGINE_NATIVE,
        end_line=end_position[0] if end_position is not None else None,
        end_column=end_position[1] if end_position is not None else None,
        remediation=remediation,
        fix=fix,
        fix_unavailable_reason=fix_unavailable_reason,
    )


def _authored_fix(*, raw_fix: object, code: str, body: LintBody) -> LintEdit | None:
    """Map a native edit only when both boundaries remain contiguous authored source."""

    if raw_fix is None:
        return None
    if not isinstance(raw_fix, dict):
        raise NativeLintError("native lint diagnostic fix must be an object")
    payload: dict[str, object] = cast("dict[str, object]", raw_fix)
    start: object = payload.get("start")
    end: object = payload.get("end")
    replacement: object = payload.get("replacement")
    if (
        not isinstance(start, int)
        or isinstance(start, bool)
        or not isinstance(end, int)
        or isinstance(end, bool)
        or not isinstance(replacement, str)
        or start < 0
        or end <= start
        or end > len(body.lint_text)
    ):
        raise NativeLintError("native lint diagnostic has an invalid fix edit")
    mapped_start: MappedOffset = map_expanded_offset(offset=start, passes=body.passes)
    mapped_last: MappedOffset = map_expanded_offset(offset=end - 1, passes=body.passes)
    if (
        mapped_start.generated
        or mapped_last.generated
        or mapped_last.offset - mapped_start.offset != end - start - 1
    ):
        return None
    return LintEdit(
        file_path=body.file_path,
        code=code,
        start=body.body_start + mapped_start.offset,
        end=body.body_start + mapped_last.offset + 1,
        replacement=replacement,
    )


def _authored_end_position(
    *,
    start: int,
    end: int,
    mapped_start: MappedOffset,
    absolute_start: int,
    body: LintBody,
    contents: str,
    line_starts: tuple[int, ...],
) -> tuple[int, int] | None:
    """Map a native exclusive end offset only when authored continuity is provable."""

    if mapped_start.generated:
        token: str | None = interpolation_text_at(body=contents, start=absolute_start)
        if token is None:
            return None
        return _offset_position(offset=absolute_start + len(token), line_starts=line_starts)
    if end <= start:
        return None
    mapped_last: MappedOffset = map_expanded_offset(offset=end - 1, passes=body.passes)
    if mapped_last.generated or mapped_last.offset - mapped_start.offset != end - start - 1:
        return None
    absolute_end: int = body.body_start + mapped_last.offset + 1
    return _offset_position(offset=absolute_end, line_starts=line_starts)


def _violation_message(
    *, message: str, mapped: MappedOffset, contents: str, absolute_offset: int
) -> str:
    if not mapped.generated:
        return message
    token: str | None = interpolation_text_at(body=contents, start=absolute_offset)
    if token is None:
        return f"{message} {GENERATED_SQL_MESSAGE_SUFFIX}"
    return f"{message} {GENERATED_SQL_MESSAGE_TEMPLATE.format(token=token)}"


def _line_starts(value: str) -> tuple[int, ...]:
    return (
        0,
        *(index + 1 for index, character in enumerate(value) if character == _NEWLINE_CHARACTER),
    )


def _offset_position(*, offset: int, line_starts: tuple[int, ...]) -> tuple[int, int]:
    line_index: int = bisect_right(line_starts, offset) - 1
    return line_index + 1, offset - line_starts[line_index] + 1
