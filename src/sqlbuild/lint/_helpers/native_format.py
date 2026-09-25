"""Safe SQLBuild-owned formatting over the native Polyglot boundary."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import sqlbuild._native as _native
from sqlbuild.lint._helpers.headers import lint_body_ranges, scan_headers
from sqlbuild.lint._helpers.sqlbuild_tokens import neutralize_interpolation, restore_interpolation
from sqlbuild.lint.constants import (
    CARRIAGE_RETURN_LINE_FEED,
    LINE_FEED,
)
from sqlbuild.lint.exceptions import NativeLintError
from sqlbuild.lint.models import HeaderSpan, InterpolationSite, LintConfig

_NATIVE_FORMAT_API_VERSION: int = 1


@dataclass(frozen=True)
class _PreparedBody:
    """One authored SQL body prepared for batched native formatting."""

    start: int
    end: int
    trailing: str
    cache_key: tuple[str, str]
    interpolation_sites: tuple[InterpolationSite, ...]


def with_newline_style(*, contents: str, newline: str) -> str:
    """Normalize generated contents back to the authored newline convention."""

    normalized: str = contents.replace(CARRIAGE_RETURN_LINE_FEED, LINE_FEED)
    if newline == LINE_FEED:
        return normalized
    return normalized.replace(LINE_FEED, newline)


def format_native_sql_bodies(
    *, files: dict[Path, str], config: LintConfig, project_dir: Path
) -> dict[Path, str]:
    """Format supported SQL bodies while leaving declined bodies unchanged."""

    prepared_by_path: dict[Path, tuple[_PreparedBody, ...]] = {}
    requests_by_key: dict[tuple[str, str], dict[str, object]] = {}
    for file_path, contents in sorted(files.items()):
        headers: tuple[HeaderSpan, ...] = scan_headers(contents=contents)
        body_ranges: tuple[tuple[int, int], ...] = lint_body_ranges(
            contents=contents,
            headers=headers,
            file_path=file_path,
            project_dir=project_dir,
        )
        prepared_bodies: list[_PreparedBody] = []
        for body_start, body_end in body_ranges:
            body: str = contents[body_start:body_end]
            trailing: str = body[len(body.rstrip()) :]
            core: str = body[: len(body) - len(trailing)] if trailing else body
            neutralized, sites = neutralize_interpolation(body=core, dialect=config.dialect)
            cache_key: tuple[str, str] = (neutralized, config.dialect)
            requests_by_key.setdefault(
                cache_key,
                {
                    "version": _NATIVE_FORMAT_API_VERSION,
                    "sql": neutralized,
                    "dialect": config.dialect,
                },
            )
            prepared_bodies.append(
                _PreparedBody(
                    start=body_start,
                    end=body_end,
                    trailing=trailing,
                    cache_key=cache_key,
                    interpolation_sites=sites,
                )
            )
        prepared_by_path[file_path] = tuple(prepared_bodies)
    response_cache: dict[tuple[str, str], dict[str, Any]] = _format_responses(
        requests_by_key=requests_by_key
    )
    formatted_files: dict[Path, str] = {}
    for file_path, contents in sorted(files.items()):
        updated: str = contents
        for prepared in reversed(prepared_by_path[file_path]):
            response: dict[str, Any] = response_cache[prepared.cache_key]
            raw_sql: object = response.get("sql")
            changed: object = response.get("changed")
            formatted: object = response.get("formatted")
            if (
                not isinstance(raw_sql, str)
                or not isinstance(changed, bool)
                or not isinstance(formatted, bool)
            ):
                raise NativeLintError("native formatter returned invalid SQL or changed state")
            if not formatted:
                continue
            if not changed:
                continue
            restored: str = restore_interpolation(
                fixed=raw_sql,
                sites=prepared.interpolation_sites,
            )
            updated = (
                f"{updated[: prepared.start]}{restored}{prepared.trailing}{updated[prepared.end :]}"
            )
        if updated != contents:
            formatted_files[file_path] = updated
    return formatted_files


def _format_responses(
    *, requests_by_key: dict[tuple[str, str], dict[str, object]]
) -> dict[tuple[str, str], dict[str, Any]]:
    if not requests_by_key:
        return {}
    ordered_requests: tuple[tuple[tuple[str, str], dict[str, object]], ...] = tuple(
        sorted(requests_by_key.items())
    )
    try:
        decoded: object = json.loads(
            _native.format_sql_batch_json(
                json.dumps(
                    [request for _, request in ordered_requests],
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
        )
    except (TypeError, ValueError) as error:
        raise NativeLintError(str(error)) from error
    if not isinstance(decoded, list) or len(decoded) != len(ordered_requests):
        raise NativeLintError("native formatter returned an invalid batch response")
    responses: dict[tuple[str, str], dict[str, Any]] = {}
    for (cache_key, _), raw_response in zip(ordered_requests, decoded, strict=True):
        if not isinstance(raw_response, dict):
            raise NativeLintError("native formatter returned a non-object response")
        response: dict[str, Any] = {str(key): value for key, value in raw_response.items()}
        if response.get("version") != _NATIVE_FORMAT_API_VERSION:
            raise NativeLintError("native formatter returned an unsupported response version")
        responses[cache_key] = response
    return responses
