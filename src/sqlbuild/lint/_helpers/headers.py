"""Lintable body ranges of SQL files by project role."""

from __future__ import annotations

from pathlib import Path, PurePath

from sqlbuild._native import (
    measurement_body_ranges,
    named_declaration_role_kind,
    sql_body_ranges,
)
from sqlbuild.compiler.compile.constants import HOOK_DIRECTORY_NAME
from sqlbuild.compiler.scopes.types import DeclarationKind
from sqlbuild.lint.models import HeaderSpan, LintFileRole


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
