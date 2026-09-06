"""Deterministic lint edit planning, validation, and atomic persistence."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from sqlbuild.compiler.compile.models import SqlExpansionContext
from sqlbuild.lint._helpers.expansion import prepare_lint_body
from sqlbuild.lint._helpers.headers import lint_body_ranges, scan_headers
from sqlbuild.lint._helpers.native import format_native_headers, lint_native_headers
from sqlbuild.lint._helpers.native_sql import run_native_sql_lint
from sqlbuild.lint.constants import FIX_STATUS_APPLIED
from sqlbuild.lint.models import (
    HeaderSpan,
    LintBody,
    LintConfig,
    LintEdit,
    LintFixRecord,
    LintViolation,
)


def apply_header_repairs(
    *, files: dict[Path, str], config: LintConfig
) -> tuple[dict[Path, str], list[LintFixRecord]]:
    repaired: dict[Path, str] = {}
    records: list[LintFixRecord] = []
    for file_path, contents in sorted(files.items()):
        before: tuple[LintViolation, ...] = lint_native_headers(
            contents=contents,
            file_path=file_path,
            headers=scan_headers(contents=contents),
            config=config,
        )
        updated, _faults = format_native_headers(
            contents=contents,
            file_path=file_path,
            config=config,
        )
        repaired[file_path] = updated
        after_codes: set[str] = {
            violation.code
            for violation in lint_native_headers(
                contents=updated,
                file_path=file_path,
                headers=scan_headers(contents=updated),
                config=config,
            )
        }
        records.extend(
            fix_record(violation=violation, status=FIX_STATUS_APPLIED, reason=None)
            for violation in before
            if violation.code not in after_codes
        )
    return repaired, records


def lint_contents(
    *,
    files: dict[Path, str],
    config: LintConfig,
    context: SqlExpansionContext | None,
    project_dir: Path,
) -> list[LintViolation]:
    violations: list[LintViolation] = []
    bodies: list[LintBody] = []
    for file_path, contents in sorted(files.items()):
        headers: tuple[HeaderSpan, ...] = scan_headers(contents=contents)
        violations.extend(
            lint_native_headers(
                contents=contents,
                file_path=file_path,
                headers=headers,
                config=config,
            )
        )
        if context is None:
            continue
        for body_start, body_end in lint_body_ranges(
            contents=contents,
            headers=headers,
            file_path=file_path,
            project_dir=project_dir,
        ):
            bodies.append(
                prepare_lint_body(
                    project_dir=project_dir,
                    file_path=file_path,
                    contents=contents,
                    body_start=body_start,
                    body_end=body_end,
                    context=context,
                )
            )
    if bodies:
        native: dict[Path, tuple[LintViolation, ...]] = run_native_sql_lint(
            bodies=tuple(bodies),
            contents_by_path=files,
            config=config,
        )
        for entries in native.values():
            violations.extend(entries)
    return violations


def planned_edits(
    *, violations: list[LintViolation]
) -> tuple[dict[Path, tuple[LintEdit, ...]], list[LintFixRecord]]:
    selected: dict[Path, list[LintEdit]] = {}
    records: list[LintFixRecord] = []
    for violation in violations:
        if violation.fix is None:
            continue
        existing: list[LintEdit] = selected.setdefault(violation.file_path, [])
        if any(overlaps(left=violation.fix, right=edit) for edit in existing):
            continue
        existing.append(violation.fix)
        records.append(fix_record(violation=violation, status=FIX_STATUS_APPLIED, reason=None))
    return (
        {
            path: tuple(sorted(edits, key=lambda edit: (edit.start, edit.end, edit.code)))
            for path, edits in selected.items()
        },
        records,
    )


def fix_record(*, violation: LintViolation, status: str, reason: str | None) -> LintFixRecord:
    return LintFixRecord(
        file_path=violation.file_path,
        code=violation.code,
        line=violation.line,
        column=violation.column,
        status=status,
        reason=reason,
    )


def apply_edits(
    *, files: dict[Path, str], edits: dict[Path, tuple[LintEdit, ...]]
) -> dict[Path, str]:
    updated: dict[Path, str] = dict(files)
    for path, path_edits in edits.items():
        contents: str = files[path]
        for edit in reversed(path_edits):
            contents = contents[: edit.start] + edit.replacement + contents[edit.end :]
        updated[path] = contents
    return updated


def write_atomically(*, path: Path, contents: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path: Path = Path(temporary_name)
    try:
        os.fchmod(descriptor, path.stat().st_mode)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            _ = handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def overlaps(*, left: LintEdit, right: LintEdit) -> bool:
    return left.start < right.end and right.start < left.end
