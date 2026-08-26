"""Folder browse, move preview, and serialization report operations."""

from __future__ import annotations

import json
from collections.abc import Mapping, Set
from dataclasses import fields, is_dataclass, replace
from enum import Enum
from pathlib import PurePath, PurePosixPath

from sqlbuild.compiler.scopes._helpers.identities import format_identity
from sqlbuild.compiler.scopes._helpers.paths import is_equal_or_descendant, normalize_path
from sqlbuild.compiler.scopes._helpers.report_projection import (
    declaration_report,
    diagnostic_projection,
)
from sqlbuild.compiler.scopes._helpers.report_query import (
    _classify,
    _ownership_roots,
    _resource_path_is_valid,
)
from sqlbuild.compiler.scopes._helpers.visibility import query_target
from sqlbuild.compiler.scopes.constants import (
    CURRENT_PATH_COMPONENT,
    GLOBAL_ALL_POLICY,
    KIND_COUNTS_FIELD,
    LIST_SECTION,
    METADATA_FIELD,
    QUALIFIED_IDENTITY_SEPARATOR,
)
from sqlbuild.compiler.scopes.exceptions import (
    InvalidQualifiedIdentityError,
    InvalidScopePathError,
    ScopeError,
)
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    DeclarationRecord,
    DeclarationReport,
    MovePreview,
    OwnershipRoot,
    ResourceIdentity,
    ResourceRecord,
    ScopeBrowseResult,
    ScopeDiagnostic,
    ScopeFolder,
    ScopeListResult,
    ScopeLookup,
    ScopeReport,
    ScopeReportFilters,
    ScopeSection,
    ScopeTargetQuery,
    VisibilityProvenance,
)
from sqlbuild.compiler.scopes.types import ScopeDiagnosticCode, ScopeKind


def browse_folders(
    *,
    lookup: ScopeLookup,
    folder: str = ".",
    target: str | PurePath | ResourceIdentity | None = None,
    target_is_prospective: bool = False,
) -> ScopeBrowseResult:
    """Return only direct child declaration-definition folders."""

    normalized, diagnostic = _folder_path(folder=folder)
    if diagnostic is not None:
        return ScopeBrowseResult(folder, (), (diagnostic,), False)
    used_identities, target_diagnostics, usage_complete = _target_used_identities(
        lookup=lookup,
        target=target,
        prospective=target_is_prospective,
    )
    paths: dict[str, list[DeclarationRecord]] = {}
    for record in lookup.index.declarations:
        definition_folder: str = _definition_folder(record=record)
        parts: tuple[str, ...] = PurePosixPath(definition_folder).parts
        parent_parts: tuple[str, ...] = (
            () if normalized == CURRENT_PATH_COMPONENT else PurePosixPath(normalized).parts
        )
        if parts[: len(parent_parts)] != parent_parts or len(parts) <= len(parent_parts):
            continue
        child: str = PurePosixPath(*parts[: len(parent_parts) + 1]).as_posix()
        paths.setdefault(child, []).append(record)
    folders: tuple[ScopeFolder, ...] = tuple(
        _folder_report(
            path=path,
            records=records,
            used_identities=used_identities,
        )
        for path, records in sorted(paths.items())
    )
    diagnostics: tuple[ScopeDiagnostic, ...] = (
        *lookup.index.diagnostics,
        *target_diagnostics,
    )
    return ScopeBrowseResult(
        normalized,
        folders,
        diagnostics,
        complete=(
            lookup.index.completeness.discovery and usage_complete and not target_diagnostics
        ),
    )


def list_folder(
    *,
    lookup: ScopeLookup,
    folder: str,
    filters: ScopeReportFilters | None = None,
    target: str | PurePath | ResourceIdentity | None = None,
    target_is_prospective: bool = False,
) -> ScopeListResult:
    """List declarations recursively beneath one definition folder."""

    selected_filters: ScopeReportFilters = filters or ScopeReportFilters(globals=GLOBAL_ALL_POLICY)
    normalized, diagnostic = _folder_path(folder=folder)
    if diagnostic is not None:
        section: ScopeSection = ScopeSection(
            LIST_SECTION, 0, 0, complete=False, page_size=selected_filters.page_size
        )
        return ScopeListResult(folder, (), section, (diagnostic,))
    used_identities, target_diagnostics, usage_complete = _target_used_identities(
        lookup=lookup,
        target=target,
        prospective=target_is_prospective,
    )
    records: list[DeclarationRecord] = [
        record
        for record in lookup.index.declarations
        if is_equal_or_descendant(path=_definition_folder(record=record), ancestor=normalized)
    ]
    if selected_filters.kinds:
        records = [record for record in records if record.identity.kind in selected_filters.kinds]
    if selected_filters.used_only:
        records = [record for record in records if record.identity in used_identities]
    if selected_filters.defined_under is not None:
        try:
            under: str = normalize_path(path=selected_filters.defined_under)
            records = [
                record
                for record in records
                if is_equal_or_descendant(path=record.path, ancestor=under)
            ]
        except InvalidScopePathError:
            records = []
    if selected_filters.glob is not None:
        from fnmatch import fnmatchcase

        records = [
            record
            for record in records
            if fnmatchcase(record.identity.name, selected_filters.glob)
            or fnmatchcase(format_identity(identity=record.identity), selected_filters.glob)
        ]
    records.sort(key=lambda item: (format_identity(identity=item.identity), item.path))
    cursor: str | None = selected_filters.cursor
    if cursor is not None and QUALIFIED_IDENTITY_SEPARATOR not in cursor:
        candidates: list[DeclarationRecord] = [
            item for item in records if item.identity.name == cursor
        ]
        cursor = format_identity(identity=candidates[0].identity) if len(candidates) == 1 else None
        if cursor is None:
            diagnostic: ScopeDiagnostic | None = ScopeDiagnostic(
                ScopeDiagnosticCode.INVALID_CURSOR, f"Cursor {selected_filters.cursor!r} is invalid"
            )
    start: int = 0
    if cursor is not None:
        positions: list[int] = [
            index
            for index, record in enumerate(records)
            if format_identity(identity=record.identity) == cursor
        ]
        if len(positions) == 1:
            start = positions[0] + 1
        else:
            diagnostic = ScopeDiagnostic(
                ScopeDiagnosticCode.INVALID_CURSOR, f"Cursor {cursor!r} is invalid"
            )
            start = 0
    size: int = max(selected_filters.page_size, 0)
    selected: list[DeclarationRecord] = records[start : start + size]
    reports: tuple[DeclarationReport, ...] = tuple(
        declaration_report(lookup=lookup, record=record) for record in selected
    )
    truncated: bool = start + len(selected) < len(records)
    section: ScopeSection = ScopeSection(
        LIST_SECTION,
        len(records),
        len(reports),
        truncated=truncated,
        complete=(
            lookup.index.completeness.discovery and usage_complete and not target_diagnostics
        ),
        next_cursor=reports[-1].identity if reports and truncated else None,
        cursor=cursor,
        page_size=size,
    )
    return ScopeListResult(
        normalized,
        reports,
        section,
        (
            *lookup.index.diagnostics,
            *target_diagnostics,
            *((diagnostic,) if diagnostic is not None else ()),
        ),
    )


def _definition_folder(*, record: DeclarationRecord) -> str:
    if record.scope is ScopeKind.GLOBAL:
        source_root: str = record.path.split("/", maxsplit=1)[0]
        parent: str = PurePosixPath(record.path).parent.as_posix()
        relative: str = parent.removeprefix(source_root).strip("/")
        base: str = f"global/{record.identity.kind.value}s"
        return f"{base}/{relative}" if relative and relative != CURRENT_PATH_COMPONENT else base
    return PurePosixPath(record.path).parent.as_posix()


def _folder_report(
    *,
    path: str,
    records: list[DeclarationRecord],
    used_identities: set[DeclarationIdentity],
) -> ScopeFolder:
    child_paths: set[str] = set()
    prefix_parts: tuple[str, ...] = PurePosixPath(path).parts
    for record in records:
        parts: tuple[str, ...] = PurePosixPath(_definition_folder(record=record)).parts
        if len(parts) > len(prefix_parts):
            child_paths.add(PurePosixPath(*parts[: len(prefix_parts) + 1]).as_posix())
    counts: dict[str, int] = {}
    for record in records:
        counts[record.identity.kind.value] = counts.get(record.identity.kind.value, 0) + 1
    return ScopeFolder(
        path,
        PurePosixPath(path).name,
        len(records),
        len(child_paths),
        sum(record.identity in used_identities for record in records),
        tuple(sorted(counts.items())),
    )


def _target_used_identities(
    *,
    lookup: ScopeLookup,
    target: str | PurePath | ResourceIdentity | None,
    prospective: bool,
) -> tuple[set[DeclarationIdentity], tuple[ScopeDiagnostic, ...], bool]:
    if prospective:
        return set(), (), False
    if target is None:
        return set(lookup.usages_by_declaration), (), lookup.index.completeness.runtime_usage
    try:
        query: ScopeTargetQuery = query_target(lookup=lookup, target=target)
    except (InvalidQualifiedIdentityError, InvalidScopePathError):
        return (
            set(),
            (
                ScopeDiagnostic(
                    ScopeDiagnosticCode.UNKNOWN_TARGET,
                    f"Browse/list target {target!s} is not a known resource",
                ),
            ),
            False,
        )
    if len(query.matches) != 1:
        return (
            set(),
            (
                ScopeDiagnostic(
                    ScopeDiagnosticCode.UNKNOWN_TARGET,
                    f"Browse/list target {target!s} does not resolve to exactly one resource",
                ),
            ),
            False,
        )
    return (
        {
            usage.declaration
            for usage in lookup.usages_by_consumer.get(query.matches[0].identity, ())
        },
        (),
        lookup.index.completeness.runtime_usage,
    )


def _folder_path(*, folder: str) -> tuple[str, ScopeDiagnostic | None]:
    try:
        return normalize_path(path=folder), None
    except InvalidScopePathError:
        return folder, ScopeDiagnostic(
            ScopeDiagnosticCode.INVALID_PROSPECTIVE_PATH,
            f"Folder {folder!r} is not a project-relative declaration folder",
        )


def build_move_preview(
    *, lookup: ScopeLookup, resource: str | ResourceIdentity, destination: str | PurePath
) -> tuple[MovePreview | None, tuple[ScopeDiagnostic, ...]]:
    """Return visibility deltas without mutating the lookup or index."""

    try:
        query: ScopeTargetQuery | None = query_target(lookup=lookup, target=resource)
    except (InvalidQualifiedIdentityError, InvalidScopePathError):
        query = None
    if query is None or len(query.matches) != 1:
        return None, (
            ScopeDiagnostic(
                ScopeDiagnosticCode.UNKNOWN_TARGET,
                f"Move source {resource!s} does not resolve to exactly one resource",
            ),
        )
    source: ResourceRecord = query.matches[0]
    try:
        path: str = normalize_path(path=destination)
    except InvalidScopePathError:
        return None, (_invalid_destination(destination=destination),)
    roots: tuple[OwnershipRoot, ...] = _destination_roots(lookup=lookup, source=source, path=path)
    occupants: tuple[ResourceRecord, ...] = lookup.resources_by_path.get(path, ())
    occupied: bool = bool(occupants) and path != source.path
    if len(roots) != 1 or occupied:
        return None, (_invalid_destination(destination=destination),)
    moved: ResourceRecord = replace(source, path=path, ownership_root=roots[0])
    old_direct, old_relationships, _old_unavailable = _classify(lookup=lookup, resource=source)
    new_direct, new_relationships, _new_unavailable = _classify(lookup=lookup, resource=moved)
    old_by_identity: dict[DeclarationIdentity, tuple[DeclarationRecord, VisibilityProvenance]] = {
        record.identity: (record, provenance) for record, provenance in old_direct
    }
    new_by_identity: dict[DeclarationIdentity, tuple[DeclarationRecord, VisibilityProvenance]] = {
        record.identity: (record, provenance) for record, provenance in new_direct
    }
    retained_ids: set[DeclarationIdentity] = set(old_by_identity) & set(new_by_identity)
    gained_ids: set[DeclarationIdentity] = set(new_by_identity) - set(old_by_identity)
    lost_ids: set[DeclarationIdentity] = set(old_by_identity) - set(new_by_identity)
    direct_usages: set[DeclarationIdentity] = {
        usage.declaration
        for usage in lookup.usages_by_consumer.get(source.identity, ())
        if usage.through is None
    }
    relationship_ids: set[DeclarationIdentity] = {
        record.identity for record, _provenance in old_relationships
    } & {record.identity for record, _provenance in new_relationships}
    private_ids: set[DeclarationIdentity] = {
        record.identity
        for record in lookup.index.declarations
        if record.scope is ScopeKind.PRIVATE and record.identity.owner == source.identity
    }
    return (
        MovePreview(
            resource=format_identity(identity=source.identity),
            destination=path,
            new_ownership_root=roots[0].path,
            retained=_reports(lookup=lookup, values=old_by_identity, identities=retained_ids),
            gained=_reports(lookup=lookup, values=new_by_identity, identities=gained_ids),
            lost=_reports(lookup=lookup, values=old_by_identity, identities=lost_ids),
            invalidated_usages=tuple(
                sorted(format_identity(identity=identity) for identity in lost_ids & direct_usages)
            ),
            private_retained=_private_reports(
                lookup=lookup,
                identities=private_ids,
            ),
            relationship_retained=_reports(
                lookup=lookup,
                values={item[0].identity: item for item in old_relationships},
                identities=relationship_ids,
            ),
            complete=(
                lookup.index.completeness.static_visibility
                and lookup.index.completeness.runtime_usage
                and lookup.index.completeness.relationships
            ),
        ),
        (),
    )


def serialize_result(*, result: ScopeReport | ScopeBrowseResult | ScopeListResult) -> str:
    """Serialize a schema-version-one scope result as deterministic ASCII JSON."""

    payload: object = _value(result)
    if not isinstance(payload, dict):
        raise ScopeError("Scope report serialization did not produce an object")
    payload = {"schema_version": 1, **payload}
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")) + "\n"


def serialize_report(*, report: ScopeReport) -> str:
    """Serialize the schema-version-one report payload as deterministic ASCII JSON."""

    return serialize_result(result=report)


def _reports(
    *,
    lookup: ScopeLookup,
    values: Mapping[DeclarationIdentity, tuple[DeclarationRecord, VisibilityProvenance]],
    identities: Set[DeclarationIdentity],
) -> tuple[DeclarationReport, ...]:
    reports: list[DeclarationReport] = []
    for identity in sorted(identities, key=lambda item: format_identity(identity=item)):
        record, provenance = values[identity]
        reports.append(declaration_report(lookup=lookup, record=record, visibility=provenance))
    return tuple(reports)


def _destination_roots(
    *, lookup: ScopeLookup, source: ResourceRecord, path: str
) -> tuple[OwnershipRoot, ...]:
    roots: set[OwnershipRoot] = set()
    for root in _ownership_roots(lookup=lookup):
        if (
            root.resource_kind == source.identity.kind
            and is_equal_or_descendant(path=path, ancestor=root.path)
            and _resource_path_is_valid(path=path, root=root)
        ):
            roots.add(root)
    return tuple(sorted(roots, key=lambda item: item.path))


def _private_reports(
    *, lookup: ScopeLookup, identities: Set[DeclarationIdentity]
) -> tuple[DeclarationReport, ...]:
    reports: list[DeclarationReport] = []
    for identity in sorted(identities, key=lambda item: format_identity(identity=item)):
        for record in lookup.declarations.get(identity, ()):
            reports.append(declaration_report(lookup=lookup, record=record))
    return tuple(reports)


def _invalid_destination(*, destination: str | PurePath) -> ScopeDiagnostic:
    return ScopeDiagnostic(
        ScopeDiagnosticCode.INVALID_PROSPECTIVE_PATH,
        f"Move destination {destination!s} is invalid, outside its authored resource root, "
        "or already occupied",
    )


def _value(value: object) -> object:
    if isinstance(value, ScopeDiagnostic):
        return diagnostic_projection(diagnostic=value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, PurePath):
        return value.as_posix()
    if is_dataclass(value) and not isinstance(value, type):
        result: dict[str, object] = {}
        for item in fields(value):
            field_value: object = getattr(value, item.name)
            if item.name == METADATA_FIELD and isinstance(field_value, tuple):
                result[item.name] = {str(key): _value(member) for key, member in field_value}
            elif item.name == KIND_COUNTS_FIELD and isinstance(field_value, tuple):
                result[item.name] = {str(key): count for key, count in field_value}
            else:
                result[item.name] = _value(field_value)
        return result
    if isinstance(value, tuple | list):
        return [_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _value(member) for key, member in value.items()}
    if value is None or isinstance(value, bool | int | float | str):
        return value
    raise ScopeError(f"Unsupported scope report value: {type(value).__name__}")
