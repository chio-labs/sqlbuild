"""Hand audit, SQL test and SQL hook SQL to the native resource SQL checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import sqlbuild._native as _native
from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile._helpers.assembly.semantic_shapes import binding_relation_names
from sqlbuild.compiler.compile.models import CompilerDiagnostic, CompileSqlReference
from sqlbuild.compiler.compile.types import (
    CompiledAuditView,
    CompiledModelView,
    CompiledProjectView,
    CompiledResourceType,
    DiagnosticPhase,
    DiagnosticSeverity,
)
from sqlbuild.compiler.discovery.constants import SQL_ANALYSIS_CONFIG_KEY
from sqlbuild.spec.contracts.models import SourceLocation

_MODEL_HOOK_KEYS: tuple[str, ...] = ("pre_hooks", "post_hooks")
_BUILT_IN_AUDIT_ROOT: str = "<built-in>"
_RESOURCE_TYPES: dict[str, CompiledResourceType] = {
    "audit": CompiledResourceType.AUDIT,
    "sql_test": CompiledResourceType.SQL_TEST,
    "model": CompiledResourceType.MODEL,
}

type _Span = tuple[int, int, int | None, int | None]
type _Row = tuple[str, str, bool, str, str, str, _Span, str | None, str | None]


def get_resource_sql_diagnostics(
    *,
    project: CompiledProjectView,
    shapes: dict[str, dict[str, str]],
    profile: ExpressionInferenceProfile,
) -> tuple[CompilerDiagnostic, ...]:
    """Bind audits, SQL tests and SQL hooks against the same closed shapes as models."""

    request: Any = (
        profile.sql_analysis_dialect,
        profile.quoted_identifiers_ignore_case,
        project.settings.require_sql_analysis,
        [(name, list(columns.items())) for name, columns in shapes.items()],
        [_audit_row(audit) for audit in project.audits],
        [
            (
                test.name,
                list(test.expected_model_names),
                str(test.test_file.relative_path),
                test.test_file.contents,
                test.sql_body,
                test.test_block.sql_body,
                test.test_block.header_values.get(SQL_ANALYSIS_CONFIG_KEY) is False,
            )
            for test in project.sql_tests
        ],
        [_model_row(model) for model in project.models],
        [
            (str(hook_file.relative_path), hook_file.contents)
            for hook_file in project.sql_hook_files
        ],
    )
    rows: list[_Row] = cast(
        list[_Row],
        _native.resource_sql_diagnostic_rows(cast(Any, project.binding_catalog).native, request),
    )
    paths: dict[str, Path] = {str(path): path for path in _paths(project)}
    return tuple(_diagnostic(row=row, paths=paths) for row in rows)


def _paths(project: CompiledProjectView) -> list[Path]:
    """Every path a resource SQL diagnostic can name, so rows map back to the authored `Path`."""

    paths: list[Path] = [audit.audit_file.relative_path for audit in project.audits]
    paths.extend(test.test_file.relative_path for test in project.sql_tests)
    paths.extend(model.relative_path for model in project.models)
    paths.extend(hook_file.relative_path for hook_file in project.sql_hook_files)
    return paths


def _relations(references: tuple[object, ...]) -> list[str]:
    return sorted(
        binding_relation_names(
            tuple(
                reference for reference in references if isinstance(reference, CompileSqlReference)
            )
        )
    )


def _audit_row(audit: CompiledAuditView) -> tuple[object, ...]:
    target: tuple[str, str] | None = (
        None
        if audit.attached_target_name is None
        else (str(audit.attached_target_kind), audit.attached_target_name)
    )
    return (
        audit.name,
        audit.definition_name,
        target,
        audit.attached_column_name,
        audit.audit_file.file_path.parts[:1] == (_BUILT_IN_AUDIT_ROOT,),
        str(audit.audit_file.relative_path),
        audit.audit_file.contents,
        [
            (audit.sql_body, audit.audit_block.sql_body),
            (audit.measure_sql, audit.audit_block.measure_sql),
            (audit.evidence_sql, audit.audit_block.evidence_sql),
        ],
        audit.audit_block.header_values.get(SQL_ANALYSIS_CONFIG_KEY) is False,
        _relations(audit.references),
    )


def _model_row(model: CompiledModelView) -> tuple[object, ...]:
    hooks: list[tuple[object, ...]] = []
    for hook_key in _MODEL_HOOK_KEYS:
        entries: object = model.config.values.get(hook_key)
        if not isinstance(entries, list | tuple):
            continue
        for hook_index, entry in enumerate(cast(list[object] | tuple[object, ...], entries)):
            statement: object = getattr(entry, "statement", None)
            if not isinstance(statement, str):
                continue
            hook_path: Path | None = getattr(entry, "relative_path", None)
            definition: object = getattr(entry, "definition_sql", None)
            hooks.append(
                (
                    hook_key,
                    hook_index,
                    statement,
                    None if hook_path is None else str(hook_path),
                    definition if isinstance(definition, str) else None,
                    _relations(tuple(getattr(entry, "reads", ()) or ())),
                )
            )
    return (
        model.name,
        str(model.relative_path),
        model.authored_sql,
        model.config.values.get(SQL_ANALYSIS_CONFIG_KEY) is False,
        hooks,
    )


def _diagnostic(*, row: _Row, paths: dict[str, Path]) -> CompilerDiagnostic:
    kind, name, is_error, code, message, path, span, note, help_text = row
    line, column, end_line, end_column = span
    return CompilerDiagnostic(
        phase=DiagnosticPhase.COMPILE,
        severity=DiagnosticSeverity.ERROR if is_error else DiagnosticSeverity.WARNING,
        code=code,
        message=message,
        resource_type=_RESOURCE_TYPES[kind],
        resource_name=name,
        location=SourceLocation(
            path=paths[path], line=line, column=column, end_line=end_line, end_column=end_column
        ),
        notes=() if note is None else (note,),
        help=help_text,
    )
