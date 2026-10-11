"""Scope reports answered by the native scope report engine, projected as report models."""

from __future__ import annotations

from pathlib import PurePath
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.scopes._helpers.placement import qualified_row
from sqlbuild.compiler.scopes.exceptions import (
    InvalidQualifiedIdentityError,
    InvalidScopePathError,
)
from sqlbuild.compiler.scopes.models import (
    ConstantMetadata,
    DeclarationExplanation,
    DeclarationIdentity,
    DeclarationRecord,
    DeclarationReport,
    EnumMetadata,
    MacroMetadata,
    MovePreview,
    ResourceIdentity,
    ScopeBrowseResult,
    ScopeChainEntry,
    ScopeCompleteness,
    ScopeDiagnostic,
    ScopeFolder,
    ScopeListResult,
    ScopeLookup,
    ScopeReport,
    ScopeReportFilters,
    ScopeResourceReport,
    ScopeSection,
    SourceLocation,
    VisibilityProvenance,
)
from sqlbuild.compiler.scopes.types import (
    NativeScopeBrowseRow,
    NativeScopeDeclarationRow,
    NativeScopeExplanationRow,
    NativeScopeFailureRow,
    NativeScopeFiltersRow,
    NativeScopeListRow,
    NativeScopeMoveRow,
    NativeScopeRaisedRow,
    NativeScopeReportRow,
    NativeScopeSectionRow,
    NativeScopeTargetRow,
    NativeScopeValuesRow,
    ScopeDiagnosticCode,
    ScopeQueryTarget,
)

_FAILURES: dict[str, type[Exception]] = {
    "identity": InvalidQualifiedIdentityError,
    "path": InvalidScopePathError,
    "index": IndexError,
}


def build_scope_report(
    *,
    lookup: ScopeLookup,
    target: ScopeQueryTarget | None,
    at: str | PurePath | None,
    directory: bool,
    filters: ScopeReportFilters | None,
) -> ScopeReport:
    """Query one existing target or prospective path; invalid index paths raise."""

    selected: ScopeReportFilters = filters or ScopeReportFilters()
    row, failure = _reports(lookup).report(
        (
            None if target is None else target_row(target=target),
            None if at is None else str(at),
            directory,
            filters_row(filters=selected),
        )
    )
    return _report(lookup=lookup, row=_checked(row=row, failure=failure), filters=selected)


def explain_declaration(
    *,
    lookup: ScopeLookup,
    declaration: str | DeclarationIdentity,
    target: str | PurePath | ResourceIdentity | None,
    at: str | PurePath | None,
    directory: bool,
) -> tuple[DeclarationExplanation, tuple[ScopeDiagnostic, ...]]:
    """Explain one qualified declaration in an optional resource or path context."""

    row, failure = _reports(lookup).explain(
        (
            (
                (qualified_row(identity=declaration), "")
                if isinstance(declaration, DeclarationIdentity)
                else (None, str(declaration))
            ),
            None if target is None else target_row(target=target),
            None if at is None else str(at),
            directory,
        )
    )
    explanation, diagnostics = _checked(row=row, failure=failure)
    return _explanation(row=explanation), _diagnostics(lookup=lookup, rows=diagnostics)


def browse_folders(
    *,
    lookup: ScopeLookup,
    folder: str,
    target: str | PurePath | ResourceIdentity | None,
    target_is_prospective: bool,
) -> ScopeBrowseResult:
    """The direct child declaration-definition folders of `folder`."""

    folder_text, folders, diagnostics, complete = _reports(lookup).browse(
        (
            folder,
            None if target is None else target_row(target=target),
            target_is_prospective,
            None,
        )
    )
    return _browse(lookup=lookup, row=(folder_text, folders, diagnostics, complete))


def list_folder(
    *,
    lookup: ScopeLookup,
    folder: str,
    filters: ScopeReportFilters | None,
    target: str | PurePath | ResourceIdentity | None,
    target_is_prospective: bool,
) -> ScopeListResult:
    """Declarations recursively beneath one definition folder."""

    row, failure = _reports(lookup).list(
        (
            folder,
            None if target is None else target_row(target=target),
            target_is_prospective,
            None if filters is None else filters_row(filters=filters),
        )
    )
    return _list(lookup=lookup, row=_checked(row=row, failure=failure))


def build_move_preview(
    *, lookup: ScopeLookup, resource: str | ResourceIdentity, destination: str | PurePath
) -> tuple[MovePreview | None, tuple[ScopeDiagnostic, ...]]:
    """Visibility deltas of a resource move, without mutating the lookup."""

    row, failure = _reports(lookup).move_preview((target_row(target=resource), str(destination)))
    preview, diagnostics = _checked(row=row, failure=failure)
    return (
        None if preview is None else _move(row=preview),
        _diagnostics(lookup=lookup, rows=diagnostics),
    )


def target_row(*, target: ScopeQueryTarget) -> NativeScopeTargetRow:
    """A query target as the native engine reads it."""

    if isinstance(target, (ResourceIdentity, DeclarationIdentity)):
        return qualified_row(identity=target), "", False
    return None, str(target), isinstance(target, PurePath)


def filters_row(*, filters: ScopeReportFilters) -> NativeScopeFiltersRow:
    """Report filters as the native engine reads them."""

    return (
        list(filters.sections),
        filters.include_nearby,
        filters.defined_under,
        [str(kind) for kind in filters.kinds],
        filters.glob,
        filters.used_only,
        filters.dependency_depth,
        filters.sort,
        filters.cursor,
        filters.page_size,
        filters.nearby_depth,
        filters.globals,
    )


def values_row(*, record: DeclarationRecord) -> NativeScopeValuesRow:
    """One declaration's value metadata as the native engine reads it."""

    macro: MacroMetadata | None = record.macro
    enum: EnumMetadata | None = record.enum
    constant: ConstantMetadata | None = record.constant
    return (
        None
        if macro is None
        else (
            list(macro.parameters),
            [qualified_row(identity=item) for item in macro.dependencies],
            macro.source_digest,
        ),
        None if enum is None else ([member.name for member in enum.members], enum.scalar_type),
        None
        if constant is None
        else (
            constant.logical_type,
            constant.collection_kind,
            constant.item_count,
            constant.nullable,
            constant.render_as,
        ),
    )


def _reports(lookup: ScopeLookup) -> _native.NativeScopeReports:
    completeness: ScopeCompleteness = lookup.index.completeness
    return _native.build_native_scope_reports(
        cast(_native.NativeScopeLookup, lookup.native),
        (
            [values_row(record=record) for record in lookup.index.declarations],
            (
                completeness.discovery,
                completeness.static_visibility,
                completeness.runtime_usage,
                completeness.relationships,
                completeness.placement,
                completeness.promotion_impact,
            ),
        ),
    )


def _checked[Row](*, row: Row | None, failure: NativeScopeFailureRow) -> Row:
    if failure is not None:
        kind, message = failure
        raise _FAILURES[kind](message)
    return cast("Row", row)


def _diagnostics(
    *, lookup: ScopeLookup, rows: list[NativeScopeRaisedRow]
) -> tuple[ScopeDiagnostic, ...]:
    diagnostics: list[ScopeDiagnostic] = []
    for position, raised in rows:
        if position is not None:
            diagnostics.append(lookup.index.diagnostics[position])
            continue
        code, message, path = cast("tuple[str, str, str | None]", raised)
        diagnostics.append(ScopeDiagnostic(ScopeDiagnosticCode(code), message, path=path))
    return tuple(diagnostics)


def _declaration(row: NativeScopeDeclarationRow) -> DeclarationReport:
    (
        (identity, kind, name, owner, (path, line, column), scope, owning_path),
        (visibility, inaccessible_reason, metadata),
        (consumers, dependencies, grants, required_scope, required_path, promotion_impact),
    ) = row
    return DeclarationReport(
        identity=identity,
        kind=kind,
        name=name,
        owner=owner,
        definition=SourceLocation(path, line, column),
        scope=scope,
        owning_path=owning_path,
        visibility=None if visibility is None else VisibilityProvenance(*visibility),
        inaccessible_reason=inaccessible_reason,
        metadata=tuple(metadata),
        consumers=tuple(consumers),
        dependencies=tuple(dependencies),
        grants=tuple(grants),
        required_scope=required_scope,
        required_path=required_path,
        promotion_impact=tuple(promotion_impact),
    )


def _declarations(rows: list[NativeScopeDeclarationRow]) -> tuple[DeclarationReport, ...]:
    return tuple(_declaration(row) for row in rows)


def _section(row: NativeScopeSectionRow) -> ScopeSection:
    return ScopeSection(*row)


def _explanation(*, row: NativeScopeExplanationRow) -> DeclarationExplanation:
    declaration, complete = row
    return DeclarationExplanation(
        None if declaration is None else _declaration(declaration), complete
    )


def _move(*, row: NativeScopeMoveRow) -> MovePreview:
    resource, destination, root, retained, gained, lost, invalidated, private, related, done = row
    return MovePreview(
        resource=resource,
        destination=destination,
        new_ownership_root=root,
        retained=_declarations(retained),
        gained=_declarations(gained),
        lost=_declarations(lost),
        invalidated_usages=tuple(invalidated),
        private_retained=_declarations(private),
        relationship_retained=_declarations(related),
        complete=done,
    )


def _report(
    *,
    lookup: ScopeLookup,
    row: NativeScopeReportRow[NativeScopeRaisedRow],
    filters: ScopeReportFilters,
) -> ScopeReport:
    (
        resource,
        chain,
        available,
        used,
        relationship_scope,
        nearby,
        _filters,
        sections,
        explanation,
        move,
        diagnostics,
        complete,
    ) = row
    return ScopeReport(
        resource=ScopeResourceReport(*resource),
        scope_chain=tuple(ScopeChainEntry(*entry) for entry in chain),
        available=_declarations(available),
        used=_declarations(used),
        relationship_scope=_declarations(relationship_scope),
        nearby_unavailable=_declarations(nearby),
        filters=filters,
        sections=tuple(_section(section) for section in sections),
        explanation=None if explanation is None else _explanation(row=explanation),
        move_preview=None if move is None else _move(row=move),
        diagnostics=_diagnostics(lookup=lookup, rows=diagnostics),
        complete=complete,
    )


def _browse(
    *, lookup: ScopeLookup, row: NativeScopeBrowseRow[NativeScopeRaisedRow]
) -> ScopeBrowseResult:
    folder, folders, diagnostics, complete = row
    return ScopeBrowseResult(
        folder,
        tuple(
            ScopeFolder(path, name, descendants, children, used, tuple(kinds))
            for path, name, descendants, children, used, kinds in folders
        ),
        _diagnostics(lookup=lookup, rows=diagnostics),
        complete,
    )


def _list(*, lookup: ScopeLookup, row: NativeScopeListRow[NativeScopeRaisedRow]) -> ScopeListResult:
    folder, declarations, section, diagnostics = row
    return ScopeListResult(
        folder,
        _declarations(declarations),
        _section(section),
        _diagnostics(lookup=lookup, rows=diagnostics),
    )
