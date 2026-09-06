"""Python boundary for SQLBuild-owned Polyglot-backed native SQL lint."""

from __future__ import annotations

import json
from bisect import bisect_right
from pathlib import Path
from typing import Any, cast

import sqlbuild._native as _native
from sqlbuild.compiler.compile.main.map_expanded_offset import map_expanded_offset
from sqlbuild.compiler.compile.models import MappedOffset
from sqlbuild.lint._helpers.sqlbuild_tokens import interpolation_text_at
from sqlbuild.lint.constants import (
    GENERATED_SQL_MESSAGE_SUFFIX,
    GENERATED_SQL_MESSAGE_TEMPLATE,
    LINT_ENGINE_NATIVE,
    VIOLATION_SEVERITY_WARNING,
)
from sqlbuild.lint.exceptions import NativeLintError
from sqlbuild.lint.models import LintBody, LintConfig, LintViolation

_NATIVE_LINT_API_VERSION: int = 1
_NEWLINE_CHARACTER: str = "\n"


def run_native_sql_lint(
    *,
    bodies: tuple[LintBody, ...],
    contents_by_path: dict[Path, str],
    config: LintConfig,
) -> dict[Path, tuple[LintViolation, ...]]:
    """Lint expanded bodies in Rust and map diagnostics to authored source."""

    violations_by_file: dict[Path, list[LintViolation]] = {}
    response_cache: dict[tuple[str, str, tuple[str, ...] | None], dict[str, Any]] = {}
    for body in bodies:
        payload: dict[str, object] = {
            "version": _NATIVE_LINT_API_VERSION,
            "sql": body.lint_text,
            "dialect": config.dialect,
        }
        if config.enabled_native_rules is not None:
            payload["enabled_rules"] = list(config.enabled_native_rules)
        cache_key: tuple[str, str, tuple[str, ...] | None] = (
            body.lint_text,
            config.dialect,
            config.enabled_native_rules,
        )
        response: dict[str, Any] | None = response_cache.get(cache_key)
        if response is None:
            response = _native_response(payload=payload)
            response_cache[cache_key] = response
        raw_diagnostics: object = response.get("diagnostics")
        if not isinstance(raw_diagnostics, list):
            raise NativeLintError("native lint response is missing a diagnostics list")
        for raw_diagnostic in raw_diagnostics:
            violations_by_file.setdefault(body.file_path, []).append(
                _authored_violation(
                    raw_diagnostic=raw_diagnostic,
                    body=body,
                    contents=contents_by_path[body.file_path],
                )
            )
    return {path: tuple(entries) for path, entries in violations_by_file.items()}


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


def _authored_violation(*, raw_diagnostic: object, body: LintBody, contents: str) -> LintViolation:
    if not isinstance(raw_diagnostic, dict):
        raise NativeLintError("native lint diagnostic must be an object")
    diagnostic: dict[str, object] = cast("dict[str, object]", raw_diagnostic)
    code: object = diagnostic.get("code")
    message: object = diagnostic.get("message")
    start: object = diagnostic.get("start")
    end: object = diagnostic.get("end")
    if (
        not isinstance(code, str)
        or not isinstance(message, str)
        or not isinstance(start, int)
        or isinstance(start, bool)
        or not isinstance(end, int)
        or isinstance(end, bool)
        or start < 0
        or end < start
        or end > len(body.lint_text)
    ):
        raise NativeLintError("native lint diagnostic has invalid code, message, or source span")
    mapped: MappedOffset = map_expanded_offset(offset=start, passes=body.passes)
    absolute_offset: int = body.body_start + mapped.offset
    starts: tuple[int, ...] = _line_starts(contents)
    line_index: int = bisect_right(starts, absolute_offset) - 1
    return LintViolation(
        file_path=body.file_path,
        line=line_index + 1,
        column=absolute_offset - starts[line_index] + 1,
        code=code,
        message=_violation_message(
            message=message,
            mapped=mapped,
            contents=contents,
            absolute_offset=absolute_offset,
        ),
        severity=VIOLATION_SEVERITY_WARNING,
        engine=LINT_ENGINE_NATIVE,
    )


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
