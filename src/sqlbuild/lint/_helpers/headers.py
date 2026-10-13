"""Lintable body ranges of SQL files by project role, and externally resolved descriptions."""

from __future__ import annotations

from pathlib import Path, PurePath

from sqlbuild._native import measurement_body_ranges, sql_body_ranges
from sqlbuild.compiler.compile.classes.model_description_resolution import (
    ModelDescriptionResolution,
)
from sqlbuild.compiler.compile.constants import HOOK_DIRECTORY_NAME
from sqlbuild.compiler.discovery.main.named_declaration_role_kind import (
    named_declaration_role_kind,
)
from sqlbuild.compiler.scopes.types import DeclarationKind
from sqlbuild.lint.constants import RULE_DESCRIPTION_PRESENT
from sqlbuild.lint.models import HeaderSpan, LintFileRole, LintViolation


def lint_file_role(
    *, file_path: Path, project_dir: Path, relative_path: PurePath | None = None
) -> LintFileRole:
    """Return the path facts lint needs, reusing a caller's project-relative path."""

    if relative_path is None:
        if not file_path.is_relative_to(project_dir):
            return LintFileRole()
        relative_path = file_path.relative_to(project_dir)
    return LintFileRole(
        declaration_kind=named_declaration_role_kind(relative_path=relative_path),
        in_project=True,
        in_hook_directory=relative_path.is_relative_to(HOOK_DIRECTORY_NAME),
    )


def lint_body_ranges(
    *,
    contents: str,
    headers: tuple[HeaderSpan, ...],
    file_path: Path,
    project_dir: Path,
    role: LintFileRole | None = None,
) -> tuple[tuple[int, int], ...]:
    """Return lintable authored bodies using resource-specific DSL boundaries."""

    file_role: LintFileRole = (
        role if role is not None else lint_file_role(file_path=file_path, project_dir=project_dir)
    )
    if file_role.in_project and file_role.declaration_kind in {
        DeclarationKind.AUDIT,
        DeclarationKind.SINGULAR_AUDIT,
    }:
        measurement_ranges: tuple[tuple[int, int], ...] = measurement_body_ranges(contents=contents)
        if measurement_ranges:
            return measurement_ranges
    return sql_body_ranges(contents=contents, headers=headers)


def drop_resolved_description_faults(
    *, violations: list[LintViolation], project_dir: Path
) -> list[LintViolation]:
    """Drop `description-present` faults for models described outside their header."""

    if not any(violation.code == RULE_DESCRIPTION_PRESENT for violation in violations):
        return violations
    described: frozenset[Path] = frozenset(
        path.resolve()
        for path in ModelDescriptionResolution.externally_described_models(project_dir=project_dir)
    )
    return [
        violation
        for violation in violations
        if violation.code != RULE_DESCRIPTION_PRESENT
        or violation.file_path.resolve() not in described
    ]
