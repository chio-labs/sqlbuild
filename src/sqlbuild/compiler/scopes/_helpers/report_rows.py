"""Report models and scope indexes as the rows native serialization and projection read."""

from __future__ import annotations

from enum import Enum

import sqlbuild._native as _native
from sqlbuild.compiler.scopes._helpers.placement import qualified_row, root_row
from sqlbuild.compiler.scopes._helpers.reports import filters_row, values_row
from sqlbuild.compiler.scopes.exceptions import ScopeError
from sqlbuild.compiler.scopes.models import (
    DeclarationExplanation,
    DeclarationReport,
    MovePreview,
    ScopeBrowseResult,
    ScopeCompleteness,
    ScopeDiagnostic,
    ScopeFolder,
    ScopeIndex,
    ScopeListResult,
    ScopeReport,
    ScopeResourceReport,
    ScopeSection,
)
from sqlbuild.compiler.scopes.types import (
    JsonValue,
    NativeScopeDeclarationRow,
    NativeScopeDiagnosticRow,
    NativeScopeExplanationRow,
    NativeScopeFolderRow,
    NativeScopeMoveRow,
    NativeScopeSectionRow,
)


def serialize_result(*, result: ScopeReport | ScopeBrowseResult | ScopeListResult) -> str:
    """Deterministic schema-version-two ASCII JSON of one scope query result."""

    try:
        if isinstance(result, ScopeReport):
            return _native.serialize_scope_result_row("report", _report_row(report=result))
        if isinstance(result, ScopeBrowseResult):
            return _native.serialize_scope_result_row(
                "browse",
                (
                    result.folder,
                    [_folder_row(folder=folder) for folder in result.folders],
                    _diagnostic_rows(diagnostics=result.diagnostics),
                    result.complete,
                ),
            )
        return _native.serialize_scope_result_row(
            "list",
            (
                result.folder,
                _declaration_rows(reports=result.declarations),
                _section_row(section=result.section),
                _diagnostic_rows(diagnostics=result.diagnostics),
            ),
        )
    except ValueError as error:
        raise ScopeError(str(error)) from error


def build_projection(*, index: ScopeIndex) -> dict[str, JsonValue]:
    """Deterministic value-free metadata of one canonical index."""

    completeness: ScopeCompleteness = index.completeness
    return _native.scope_metadata_projection_rows(
        (
            [root_row(root=root) for root in index.ownership_roots],
            [
                (
                    (record.identity.kind.value, record.identity.name),
                    record.path,
                    root_row(root=record.ownership_root),
                )
                for record in index.resources
            ],
            [
                (
                    qualified_row(identity=record.identity),
                    record.path,
                    record.line,
                    record.column,
                    record.scope.value,
                    root_row(root=record.ownership_root),
                    record.owning_path,
                )
                for record in index.declarations
            ],
            [values_row(record=record) for record in index.declarations],
            [
                (
                    qualified_row(identity=usage.consumer),
                    qualified_row(identity=usage.declaration),
                    usage.kind.value,
                    None if usage.through is None else qualified_row(identity=usage.through),
                    usage.enum_member,
                )
                for usage in index.usages
            ],
            [
                (
                    (grant.resource.kind.value, grant.resource.name),
                    qualified_row(identity=grant.declaration),
                    qualified_row(identity=grant.through),
                    grant.kind.value,
                )
                for grant in index.grants
            ],
            [
                (
                    (fact.resource.kind.value, fact.resource.name),
                    qualified_row(identity=fact.declaration),
                    fact.reason.value,
                    None if fact.through is None else qualified_row(identity=fact.through),
                )
                for fact in index.visibility
            ],
            [
                (
                    (fact.resource.kind.value, fact.resource.name),
                    qualified_row(identity=fact.declaration),
                    fact.reason.value,
                    None,
                )
                for fact in index.inaccessible
            ],
            _diagnostic_rows(diagnostics=index.diagnostics),
            (
                completeness.discovery,
                completeness.static_visibility,
                completeness.runtime_usage,
                completeness.relationships,
                completeness.placement,
                completeness.promotion_impact,
            ),
        )
    )


def _folder_row(*, folder: ScopeFolder) -> NativeScopeFolderRow:
    return (
        folder.path,
        folder.name,
        folder.descendant_count,
        folder.child_count,
        folder.used_count,
        [(str(kind), count) for kind, count in folder.kind_counts],
    )


def _text(value: object) -> str:
    return str(value.value) if isinstance(value, Enum) else str(value)


def _diagnostic_rows(*, diagnostics: tuple[ScopeDiagnostic, ...]) -> list[NativeScopeDiagnosticRow]:
    return [
        (
            _text(diagnostic.code),
            diagnostic.message,
            _text(diagnostic.severity),
            diagnostic.path,
            diagnostic.line,
            diagnostic.column,
            None
            if diagnostic.declaration is None
            else qualified_row(identity=diagnostic.declaration),
            (
                None
                if diagnostic.resource is None
                else (diagnostic.resource.kind.value, diagnostic.resource.name)
            ),
        )
        for diagnostic in diagnostics
    ]


def _declaration_row(report: DeclarationReport) -> NativeScopeDeclarationRow:
    return (
        (
            report.identity,
            report.kind,
            report.name,
            report.owner,
            (report.definition.path, report.definition.line, report.definition.column),
            report.scope,
            report.owning_path,
        ),
        (
            (
                None
                if report.visibility is None
                else (report.visibility.reason, report.visibility.through)
            ),
            report.inaccessible_reason,
            [(str(key), value) for key, value in report.metadata],
        ),
        (
            list(report.consumers),
            list(report.dependencies),
            list(report.grants),
            report.required_scope,
            report.required_path,
            list(report.promotion_impact),
        ),
    )


def _declaration_rows(*, reports: tuple[DeclarationReport, ...]) -> list[NativeScopeDeclarationRow]:
    return [_declaration_row(report) for report in reports]


def _section_row(*, section: ScopeSection) -> NativeScopeSectionRow:
    return (
        section.name,
        section.total,
        section.returned,
        section.collapsed,
        section.collapsed_count,
        section.truncated,
        section.complete,
        section.next_cursor,
        section.cursor,
        section.page_size,
    )


def _explanation_row(*, explanation: DeclarationExplanation) -> NativeScopeExplanationRow:
    return (
        None if explanation.declaration is None else _declaration_row(explanation.declaration),
        explanation.complete,
    )


def _move_row(*, move: MovePreview) -> NativeScopeMoveRow:
    return (
        move.resource,
        move.destination,
        move.new_ownership_root,
        _declaration_rows(reports=move.retained),
        _declaration_rows(reports=move.gained),
        _declaration_rows(reports=move.lost),
        list(move.invalidated_usages),
        _declaration_rows(reports=move.private_retained),
        _declaration_rows(reports=move.relationship_retained),
        move.complete,
    )


def _report_row(*, report: ScopeReport) -> object:
    resource: ScopeResourceReport = report.resource
    return (
        (
            resource.target,
            resource.identity,
            resource.path,
            resource.prospective,
            resource.directory,
            resource.duplicate_count,
        ),
        [(entry.kind, entry.path, entry.declaration_count) for entry in report.scope_chain],
        _declaration_rows(reports=report.available),
        _declaration_rows(reports=report.used),
        _declaration_rows(reports=report.relationship_scope),
        _declaration_rows(reports=report.nearby_unavailable),
        filters_row(filters=report.filters),
        [_section_row(section=section) for section in report.sections],
        None if report.explanation is None else _explanation_row(explanation=report.explanation),
        None if report.move_preview is None else _move_row(move=report.move_preview),
        _diagnostic_rows(diagnostics=report.diagnostics),
        report.complete,
    )
