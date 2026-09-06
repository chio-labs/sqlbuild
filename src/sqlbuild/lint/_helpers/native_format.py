"""Safe SQLBuild-owned formatting over the native Polyglot boundary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import sqlbuild._native as _native
from sqlbuild.lint._helpers.headers import lint_body_ranges, scan_headers
from sqlbuild.lint._helpers.sqlbuild_tokens import neutralize_interpolation, restore_interpolation
from sqlbuild.lint.exceptions import NativeLintError
from sqlbuild.lint.models import HeaderSpan, LintConfig

_NATIVE_FORMAT_API_VERSION: int = 1


def format_native_sql_bodies(
    *, files: dict[Path, str], config: LintConfig, project_dir: Path
) -> dict[Path, str]:
    """Format supported authored SQL bodies and preserve unsupported bodies unchanged."""

    formatted_files: dict[Path, str] = {}
    response_cache: dict[tuple[str, str], dict[str, Any]] = {}
    for file_path, contents in sorted(files.items()):
        headers: tuple[HeaderSpan, ...] = scan_headers(contents=contents)
        updated: str = contents
        body_ranges: tuple[tuple[int, int], ...] = lint_body_ranges(
            contents=contents,
            headers=headers,
            file_path=file_path,
            project_dir=project_dir,
        )
        for body_start, body_end in reversed(body_ranges):
            body: str = contents[body_start:body_end]
            trailing: str = body[len(body.rstrip()) :]
            core: str = body[: len(body) - len(trailing)] if trailing else body
            neutralized, sites = neutralize_interpolation(body=core)
            cache_key: tuple[str, str] = (neutralized, config.dialect)
            response: dict[str, Any] | None = response_cache.get(cache_key)
            if response is None:
                response = _format_response(
                    sql=neutralized,
                    dialect=config.dialect,
                )
                response_cache[cache_key] = response
            raw_sql: object = response.get("sql")
            changed: object = response.get("changed")
            if not isinstance(raw_sql, str) or not isinstance(changed, bool):
                raise NativeLintError("native formatter returned invalid SQL or changed state")
            if not changed:
                continue
            restored: str = restore_interpolation(fixed=raw_sql, sites=sites)
            updated = f"{updated[:body_start]}{restored}{trailing}{updated[body_end:]}"
        if updated != contents:
            formatted_files[file_path] = updated
    return formatted_files


def _format_response(*, sql: str, dialect: str) -> dict[str, Any]:
    payload: dict[str, object] = {
        "version": _NATIVE_FORMAT_API_VERSION,
        "sql": sql,
        "dialect": dialect,
    }
    try:
        decoded: object = json.loads(
            _native.format_sql_json(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        )
    except (TypeError, ValueError) as error:
        raise NativeLintError(str(error)) from error
    if not isinstance(decoded, dict):
        raise NativeLintError("native formatter returned a non-object response")
    if decoded.get("version") != _NATIVE_FORMAT_API_VERSION:
        raise NativeLintError("native formatter returned an unsupported response version")
    return {str(key): value for key, value in decoded.items()}
