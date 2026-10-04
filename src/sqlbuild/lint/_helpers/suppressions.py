"""Reason-required local suppression handling for lint diagnostics."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path

from sqlbuild.errors.setting_help.main.setting_help import setting_help
from sqlbuild.errors.setting_help.main.setting_note import setting_note
from sqlbuild.lint.constants import (
    ALLOW_EXCEPTIONS_KEY,
    LINT_ENGINE_NATIVE,
    PROJECT_CONFIG_FILENAME_KEY,
    RULES_SECTION_KEY,
    VIOLATION_SEVERITY_FAULT,
    VIOLATION_SEVERITY_WARNING,
)
from sqlbuild.lint.models import LintEdit, LintViolation

_SUPPRESSION_PREFIX: str = "sqb: ignore"
_SUPPRESSION_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*--\s*sqb:\s*ignore\s+(?P<code>[A-Za-z0-9_-]+)\s+because\s+(?P<reason>\S.*)\s*$"
)
_SUPPRESSION_DIAGNOSTIC_CODE: str = "SQBRSQL000"


@dataclass(frozen=True)
class _Suppression:
    code: str
    directive_line: int
    target_line: int


def apply_suppressions(
    *,
    violations: list[LintViolation],
    contents_by_path: dict[Path, str],
    allow_suppressions: bool,
) -> list[LintViolation]:
    """Remove matching next-line diagnostics, or reject every directive when forbidden."""

    retained: list[LintViolation] = list(violations)
    for file_path, contents in contents_by_path.items():
        suppressions, invalid = _parse_suppressions(file_path=file_path, contents=contents)
        if not allow_suppressions:
            directive_lines: set[int] = {violation.line for violation in invalid}
            directive_lines.update(suppression.directive_line for suppression in suppressions)
            retained.extend(
                _forbidden_violation(file_path=file_path, line=line, contents=contents)
                for line in sorted(directive_lines)
            )
            continue
        retained.extend(invalid)
        for suppression in suppressions:
            match_index: int | None = next(
                (
                    index
                    for index, violation in enumerate(retained)
                    if violation.file_path == file_path
                    and violation.line == suppression.target_line
                    and violation.code == suppression.code
                    and violation.engine == LINT_ENGINE_NATIVE
                    and violation.code.startswith("SQBRSQL")
                ),
                None,
            )
            if match_index is None:
                retained.append(
                    _suppression_violation(
                        file_path=file_path,
                        line=suppression.directive_line,
                        message=f"Unused suppression for {suppression.code}",
                        remediation="Remove the stale suppression directive.",
                        contents=contents,
                        fixable=True,
                    )
                )
            else:
                retained.pop(match_index)
    return retained


def _parse_suppressions(
    *, file_path: Path, contents: str
) -> tuple[tuple[_Suppression, ...], tuple[LintViolation, ...]]:
    lines: list[str] = contents.splitlines()
    suppressions: list[_Suppression] = []
    invalid: list[LintViolation] = []
    for index, line in enumerate(lines):
        if _SUPPRESSION_PREFIX not in line.lower():
            continue
        match: re.Match[str] | None = _SUPPRESSION_PATTERN.match(line)
        if match is None:
            invalid.append(
                _suppression_violation(
                    file_path=file_path,
                    line=index + 1,
                    message="Suppression directive is invalid",
                    remediation="Use '-- sqb: ignore CODE because <reason>'.",
                    contents=contents,
                    fixable=False,
                )
            )
            continue
        target_index: int = index + 1
        while target_index < len(lines) and (
            not lines[target_index].strip() or lines[target_index].lstrip().startswith("--")
        ):
            target_index += 1
        suppressions.append(
            _Suppression(
                code=match.group("code"),
                directive_line=index + 1,
                target_line=target_index + 1,
            )
        )
    return tuple(suppressions), tuple(invalid)


def _forbidden_violation(*, file_path: Path, line: int, contents: str) -> LintViolation:
    violation: LintViolation = _suppression_violation(
        file_path=file_path,
        line=line,
        message="Inline Rule suppressions are not allowed in this project",
        remediation=(
            "Remove the directive and fix the finding it suppresses; "
            + setting_note(
                file_name=PROJECT_CONFIG_FILENAME_KEY,
                section=RULES_SECTION_KEY,
                key=ALLOW_EXCEPTIONS_KEY,
                value=False,
            )
            + ". "
            + setting_help(
                purpose="To allow inline suppressions",
                file_name=PROJECT_CONFIG_FILENAME_KEY,
                section=RULES_SECTION_KEY,
                key=ALLOW_EXCEPTIONS_KEY,
                value=True,
            )
        ),
        contents=contents,
        fixable=False,
    )
    return replace(
        violation,
        severity=VIOLATION_SEVERITY_FAULT,
        fix_unavailable_reason="removing the directive exposes the finding it suppresses",
    )


def _suppression_violation(
    *,
    file_path: Path,
    line: int,
    message: str,
    remediation: str,
    contents: str,
    fixable: bool,
) -> LintViolation:
    start, end = _line_range(contents=contents, line=line)
    return LintViolation(
        file_path=file_path,
        line=line,
        column=1,
        code=_SUPPRESSION_DIAGNOSTIC_CODE,
        message=message,
        severity=VIOLATION_SEVERITY_WARNING,
        engine=LINT_ENGINE_NATIVE,
        remediation=remediation,
        fix=(
            LintEdit(
                file_path=file_path,
                code=_SUPPRESSION_DIAGNOSTIC_CODE,
                start=start,
                end=end,
                replacement="",
            )
            if fixable
            else None
        ),
        fix_unavailable_reason=(
            None if fixable else "a valid suppression reason requires user intent"
        ),
    )


def _line_range(*, contents: str, line: int) -> tuple[int, int]:
    lines: list[str] = contents.splitlines(keepends=True)
    start: int = sum(len(entry) for entry in lines[: line - 1])
    return start, start + len(lines[line - 1])
