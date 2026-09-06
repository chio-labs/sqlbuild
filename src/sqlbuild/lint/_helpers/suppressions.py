"""Reason-required local suppression handling for lint diagnostics."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from sqlbuild.lint.constants import LINT_ENGINE_NATIVE, VIOLATION_SEVERITY_WARNING
from sqlbuild.lint.models import LintViolation

_SUPPRESSION_PREFIX: str = "sqb: ignore"
_SUPPRESSION_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*--\s*sqb:\s*ignore\s+(?P<code>[A-Za-z0-9_-]+)\s+because\s+(?P<reason>\S.*)\s*$"
)
_SUPPRESSION_DIAGNOSTIC_CODE: str = "SQBL000"


@dataclass(frozen=True)
class _Suppression:
    code: str
    directive_line: int
    target_line: int


def apply_suppressions(
    *, violations: list[LintViolation], contents_by_path: dict[Path, str]
) -> list[LintViolation]:
    """Remove matching next-line diagnostics and report invalid or unused directives."""

    retained: list[LintViolation] = list(violations)
    for file_path, contents in contents_by_path.items():
        suppressions, invalid = _parse_suppressions(file_path=file_path, contents=contents)
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
                    and violation.code.startswith("SQBL")
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


def _suppression_violation(
    *, file_path: Path, line: int, message: str, remediation: str
) -> LintViolation:
    return LintViolation(
        file_path=file_path,
        line=line,
        column=1,
        code=_SUPPRESSION_DIAGNOSTIC_CODE,
        message=message,
        severity=VIOLATION_SEVERITY_WARNING,
        engine=LINT_ENGINE_NATIVE,
        remediation=remediation,
    )
