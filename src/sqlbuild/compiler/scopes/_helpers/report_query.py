"""Pure query engine over the canonical compiler scope lookup."""

from __future__ import annotations

from fnmatch import fnmatchcase
from pathlib import PurePath, PurePosixPath

from sqlbuild.compiler.scopes._helpers.identities import format_identity, parse_identity
from sqlbuild.compiler.scopes._helpers.paths import is_equal_or_descendant, normalize_path
from sqlbuild.compiler.scopes._helpers.report_projection import declaration_report, safe_scope_path
from sqlbuild.compiler.scopes._helpers.visibility import (
    _inaccessible_reason,
    _visibility_reason,
    query_target,
)
from sqlbuild.compiler.scopes.constants import (
    AVAILABLE_SECTION,
    CURRENT_PATH_COMPONENT,
    DECLARATION_KIND_VALUES,
    EMPTY_TEXT,
    GLOBAL_SUMMARY_POLICY,
    GLOBAL_USED_POLICY,
    PATH_SEPARATOR,
    QUALIFIED_IDENTITY_SEPARATOR,
    RELATIONSHIP_SECTION,
    USED_SECTION,
    WINDOWS_PATH_SEPARATOR,
)
from sqlbuild.compiler.scopes.exceptions import InvalidQualifiedIdentityError, InvalidScopePathError
from sqlbuild.compiler.scopes.models import (
    DeclarationExplanation,
    DeclarationIdentity,
    DeclarationRecord,
    DeclarationReport,
    GrantRecord,
    OwnershipRoot,
    ResourceIdentity,
    ResourceRecord,
    ScopeChainEntry,
    ScopeDiagnostic,
    ScopeLookup,
    ScopeReport,
    ScopeReportFilters,
    ScopeResourceReport,
    ScopeSection,
    ScopeTargetQuery,
    UsageRecord,
    VisibilityProvenance,
)
from sqlbuild.compiler.scopes.types import (
    ResourceKind,
    ScopeDiagnosticCode,
    ScopeKind,
    VisibilityReason,
)


def build_scope_report(
    *,
    lookup: ScopeLookup,
    target: str | PurePath | ResourceIdentity | DeclarationIdentity | None = None,
    at: str | PurePath | None = None,
    directory: bool = False,
    filters: ScopeReportFilters | None = None,
) -> ScopeReport:
    """Build a complete value-safe report for an existing target or prospective path."""

    selected_filters: ScopeReportFilters = filters or ScopeReportFilters()
    diagnostics: list[ScopeDiagnostic] = list(lookup.index.diagnostics)
    if at is not None:
        resource, record, target_diagnostics = _prospective_resource(
            lookup=lookup, at=at, directory=directory
        )
        diagnostics.extend(target_diagnostics)
        explanation: DeclarationExplanation | None = None
    else:
        resource, record, explanation, target_diagnostics = _existing_target(
            lookup=lookup, target=target
        )
        diagnostics.extend(target_diagnostics)
    if record is None:
        explanation_complete: bool = explanation is not None and explanation.complete
        return ScopeReport(
            resource=resource,
            filters=selected_filters,
            explanation=explanation,
            diagnostics=tuple(diagnostics),
            complete=explanation_complete,
        )

    direct, relationships, unavailable = _classify(lookup=lookup, resource=record)
    target_usages: tuple[UsageRecord, ...] = lookup.usages_by_consumer.get(record.identity, ())
    used_identities: set[DeclarationIdentity] = {usage.declaration for usage in target_usages}
    direct_used: set[DeclarationIdentity] = {
        usage.declaration for usage in target_usages if usage.through is None
    }
    relationship_used: set[DeclarationIdentity] = {
        usage.declaration for usage in target_usages if usage.through is not None
    }
    used_by_identity: dict[DeclarationIdentity, tuple[DeclarationRecord, VisibilityProvenance]] = {
        item[0].identity: item for item in direct if item[0].identity in direct_used
    }
    used_by_identity.update(
        {item[0].identity: item for item in relationships if item[0].identity in relationship_used}
    )
    used_records: tuple[tuple[DeclarationRecord, VisibilityProvenance], ...] = tuple(
        sorted(used_by_identity.values(), key=_declaration_pair_key)
    )
    nearby: tuple[tuple[DeclarationRecord, str], ...] = _nearby(
        lookup=lookup,
        resource=record,
        unavailable=unavailable,
        depth=selected_filters.nearby_depth,
    )

    direct: tuple[tuple[DeclarationRecord, VisibilityProvenance], ...] = _filter_visible(
        lookup=lookup,
        values=direct,
        filters=selected_filters,
        used_identities=used_identities,
    )
    used_records = _filter_visible(
        lookup=lookup,
        values=used_records,
        filters=selected_filters,
        used_identities=used_identities,
    )
    relationships: tuple[tuple[DeclarationRecord, VisibilityProvenance], ...] = _filter_visible(
        lookup=lookup,
        values=relationships,
        filters=selected_filters,
        used_identities=used_identities,
    )
    nearby = _filter_nearby(values=nearby, filters=selected_filters, used=used_identities)

    if AVAILABLE_SECTION not in selected_filters.sections:
        direct = ()
    if USED_SECTION not in selected_filters.sections:
        used_records = ()
    if RELATIONSHIP_SECTION not in selected_filters.sections:
        relationships = ()

    if selected_filters.dependency_depth > 0:
        used_records = _expand_dependencies(
            lookup=lookup, values=used_records, depth=selected_filters.dependency_depth
        )

    collapsed: int = 0
    if selected_filters.globals == GLOBAL_SUMMARY_POLICY:
        retained: tuple[tuple[DeclarationRecord, VisibilityProvenance], ...] = tuple(
            item
            for item in direct
            if item[0].scope is not ScopeKind.GLOBAL or item[0].identity in used_identities
        )
        collapsed = len(direct) - len(retained)
        direct = retained
    elif selected_filters.globals == GLOBAL_USED_POLICY:
        direct = tuple(
            item
            for item in direct
            if item[0].scope is not ScopeKind.GLOBAL or item[0].identity in used_identities
        )

    report_sections: tuple[tuple[tuple[DeclarationRecord, VisibilityProvenance], ...], ...] = (
        direct,
        used_records,
        relationships,
    )
    cursor, cursor_diagnostic = _resolve_cursor(
        requested=selected_filters.cursor,
        sections=report_sections,
    )
    if cursor_diagnostic is not None:
        diagnostics.append(cursor_diagnostic)
    available, available_section = _page(
        lookup=lookup,
        name=AVAILABLE_SECTION,
        values=direct,
        cursor=cursor,
        page_size=selected_filters.page_size,
        complete=lookup.index.completeness.static_visibility,
        collapsed=collapsed,
    )
    used, used_section = _page(
        lookup=lookup,
        name=USED_SECTION,
        values=used_records,
        cursor=cursor,
        page_size=selected_filters.page_size,
        complete=lookup.index.completeness.runtime_usage,
    )
    relationship_scope, relationship_section = _page(
        lookup=lookup,
        name=RELATIONSHIP_SECTION,
        values=relationships,
        cursor=cursor,
        page_size=selected_filters.page_size,
        complete=lookup.index.completeness.relationships,
    )
    nearby_reports: tuple[DeclarationReport, ...] = tuple(
        declaration_report(
            lookup=lookup,
            record=item,
            inaccessible_reason=reason,
        )
        for item, reason in nearby[: selected_filters.page_size]
    )
    nearby_section: ScopeSection = ScopeSection(
        name="nearby_unavailable",
        total=len(nearby),
        returned=len(nearby_reports),
        truncated=len(nearby_reports) < len(nearby),
        complete=lookup.index.completeness.static_visibility,
        next_cursor=(nearby_reports[-1].identity if len(nearby_reports) < len(nearby) else None),
        page_size=selected_filters.page_size,
    )
    sections: tuple[ScopeSection, ...] = (
        available_section,
        used_section,
        relationship_section,
        nearby_section,
    )
    prospective_complete: bool = not resource.prospective
    complete: bool = all(section.complete for section in sections) and prospective_complete
    if resource.prospective:
        diagnostics.append(
            ScopeDiagnostic(
                code=ScopeDiagnosticCode.INCOMPLETE_USAGE,
                message=(
                    "Runtime usage and relationship facts are unavailable for a prospective path"
                ),
                path=resource.path,
            )
        )
    return ScopeReport(
        resource=resource,
        scope_chain=_scope_chain(lookup=lookup, resource=record),
        available=available,
        used=used,
        relationship_scope=relationship_scope,
        nearby_unavailable=nearby_reports if selected_filters.include_nearby else (),
        filters=selected_filters,
        sections=sections,
        explanation=explanation,
        diagnostics=tuple(diagnostics),
        complete=complete,
    )


def explain_declaration(
    *, lookup: ScopeLookup, target: str | DeclarationIdentity, at: ResourceRecord | None = None
) -> tuple[DeclarationExplanation, tuple[ScopeDiagnostic, ...]]:
    """Explain one required kind-qualified declaration identity."""

    diagnostics: list[ScopeDiagnostic] = []
    identity: DeclarationIdentity | None = (
        target if isinstance(target, DeclarationIdentity) else None
    )
    if identity is None:
        try:
            parsed: ResourceIdentity | DeclarationIdentity = parse_identity(value=str(target))
            identity = parsed if isinstance(parsed, DeclarationIdentity) else None
        except InvalidQualifiedIdentityError:
            identity = None
    if identity is None:
        diagnostics.append(
            _diagnostic(code=ScopeDiagnosticCode.UNQUALIFIED_TARGET, value=str(target))
        )
        return DeclarationExplanation(None, False), tuple(diagnostics)
    records: tuple[DeclarationRecord, ...] = lookup.declarations.get(identity, ())
    if not records:
        diagnostics.append(
            _diagnostic(
                code=ScopeDiagnosticCode.UNKNOWN_TARGET,
                value=format_identity(identity=identity),
            )
        )
        return DeclarationExplanation(None, False), tuple(diagnostics)
    if len(records) > 1:
        diagnostics.append(
            _diagnostic(
                code=ScopeDiagnosticCode.DUPLICATE_DECLARATION,
                value=format_identity(identity=identity),
            )
        )
    record: DeclarationRecord = records[0]
    visibility: VisibilityProvenance | None = None
    inaccessible: str | None = None
    if at is not None:
        reason: VisibilityReason | None = _visibility_reason(resource=at, declaration=record)
        if reason is None:
            matching_grants: tuple[GrantRecord, ...] = tuple(
                grant
                for grant in lookup.grants_by_resource.get(at.identity, ())
                if grant.declaration == record.identity
            )
            if matching_grants:
                visibility = VisibilityProvenance(
                    VisibilityReason.EXPECTED_MODEL.value,
                    ",".join(
                        sorted(format_identity(identity=grant.through) for grant in matching_grants)
                    ),
                )
            else:
                inaccessible = _inaccessible_reason(resource=at, declaration=record).value
        else:
            visibility = VisibilityProvenance(reason.value)
    return (
        DeclarationExplanation(
            declaration_report(
                lookup=lookup,
                record=record,
                visibility=visibility,
                inaccessible_reason=inaccessible,
            ),
            lookup.index.completeness.placement,
        ),
        tuple(diagnostics),
    )


def _existing_target(
    *,
    lookup: ScopeLookup,
    target: str | PurePath | ResourceIdentity | DeclarationIdentity | None,
) -> tuple[
    ScopeResourceReport,
    ResourceRecord | None,
    DeclarationExplanation | None,
    tuple[ScopeDiagnostic, ...],
]:
    if target is None:
        diagnostic: ScopeDiagnostic = _diagnostic(
            code=ScopeDiagnosticCode.UNQUALIFIED_TARGET, value=EMPTY_TEXT
        )
        return ScopeResourceReport(EMPTY_TEXT, None, None), None, None, (diagnostic,)
    raw: str = (
        format_identity(identity=target) if not isinstance(target, (str, PurePath)) else str(target)
    )
    if isinstance(target, DeclarationIdentity) or (
        isinstance(target, str)
        and target.split(QUALIFIED_IDENTITY_SEPARATOR, maxsplit=1)[0] in DECLARATION_KIND_VALUES
    ):
        explanation, explain_diagnostics = explain_declaration(lookup=lookup, target=target)
        return ScopeResourceReport(raw, raw, None), None, explanation, explain_diagnostics
    if (
        isinstance(target, str)
        and QUALIFIED_IDENTITY_SEPARATOR not in target
        and not _looks_like_path(value=target)
    ):
        diagnostic = _diagnostic(code=ScopeDiagnosticCode.UNQUALIFIED_TARGET, value=raw)
        return ScopeResourceReport(raw, None, None), None, None, (diagnostic,)
    try:
        query: ScopeTargetQuery = query_target(lookup=lookup, target=target)
    except (InvalidQualifiedIdentityError, InvalidScopePathError):
        diagnostic = _unknown_target_diagnostic(value=raw)
        return ScopeResourceReport(raw, None, None), None, None, (diagnostic,)
    if query.unknown:
        diagnostic = _unknown_target_diagnostic(value=raw)
        return ScopeResourceReport(raw, None, None), None, None, (diagnostic,)
    target_diagnostics: tuple[ScopeDiagnostic, ...] = ()
    if len(query.matches) > 1:
        target_diagnostics = (
            ScopeDiagnostic(
                ScopeDiagnosticCode.DUPLICATE_RESOURCE,
                f"Target {raw!r} matches {len(query.matches)} resources",
            ),
        )
    record: ResourceRecord = query.matches[0]
    return (
        ScopeResourceReport(
            raw,
            format_identity(identity=record.identity),
            safe_scope_path(path=record.path),
            duplicate_count=len(query.matches),
        ),
        record,
        None,
        target_diagnostics,
    )


def _prospective_resource(
    *,
    lookup: ScopeLookup,
    at: str | PurePath,
    directory: bool,
) -> tuple[ScopeResourceReport, ResourceRecord | None, tuple[ScopeDiagnostic, ...]]:
    raw: str = str(at)
    try:
        path: str = normalize_path(path=at)
    except InvalidScopePathError:
        diagnostic: ScopeDiagnostic = _diagnostic(
            code=ScopeDiagnosticCode.INVALID_PROSPECTIVE_PATH, value=raw
        )
        return ScopeResourceReport(raw, None, None, True, directory), None, (diagnostic,)
    roots: tuple[OwnershipRoot, ...] = _ownership_roots(lookup=lookup)
    root: OwnershipRoot | None = next(
        (item for item in roots if is_equal_or_descendant(path=path, ancestor=item.path)),
        None,
    )
    if root is None or (not directory and not _resource_path_is_valid(path=path, root=root)):
        diagnostic = _diagnostic(code=ScopeDiagnosticCode.INVALID_PROSPECTIVE_PATH, value=raw)
        return ScopeResourceReport(raw, None, path, True, directory), None, (diagnostic,)
    authored_path: str = f"{path}/<direct-child>{_default_suffix(root=root)}" if directory else path
    identity: ResourceIdentity = ResourceIdentity(
        root.resource_kind or ResourceKind.MODEL, f"<path:{path}>"
    )
    record: ResourceRecord = ResourceRecord(identity, authored_path, root)
    return ScopeResourceReport(raw, None, path, True, directory), record, ()


def _classify(
    *, lookup: ScopeLookup, resource: ResourceRecord
) -> tuple[
    tuple[tuple[DeclarationRecord, VisibilityProvenance], ...],
    tuple[tuple[DeclarationRecord, VisibilityProvenance], ...],
    tuple[tuple[DeclarationRecord, str], ...],
]:
    grants: tuple[GrantRecord, ...] = lookup.grants_by_resource.get(resource.identity, ())
    granted: dict[DeclarationIdentity, tuple[str, ...]] = {}
    for grant in grants:
        granted.setdefault(grant.declaration, ())
        granted[grant.declaration] += (format_identity(identity=grant.through),)
    direct: list[tuple[DeclarationRecord, VisibilityProvenance]] = []
    relationships: list[tuple[DeclarationRecord, VisibilityProvenance]] = []
    unavailable: list[tuple[DeclarationRecord, str]] = []
    for declaration in lookup.index.declarations:
        reason: VisibilityReason | None = _visibility_reason(
            resource=resource, declaration=declaration
        )
        if reason is not None:
            direct.append((declaration, VisibilityProvenance(reason.value)))
        if declaration.identity in granted and declaration.scope is not ScopeKind.PRIVATE:
            relationships.append(
                (
                    declaration,
                    VisibilityProvenance(
                        VisibilityReason.EXPECTED_MODEL.value,
                        ",".join(sorted(granted[declaration.identity])),
                    ),
                )
            )
        elif reason is None:
            unavailable.append(
                (
                    declaration,
                    _inaccessible_reason(resource=resource, declaration=declaration).value,
                )
            )
    return (
        tuple(sorted(direct, key=_declaration_pair_key)),
        tuple(sorted(relationships, key=_declaration_pair_key)),
        tuple(sorted(unavailable, key=_declaration_pair_key)),
    )


def _filter_visible(
    *,
    lookup: ScopeLookup,
    values: tuple[tuple[DeclarationRecord, VisibilityProvenance], ...],
    filters: ScopeReportFilters,
    used_identities: set[DeclarationIdentity],
) -> tuple[tuple[DeclarationRecord, VisibilityProvenance], ...]:
    selected: tuple[tuple[DeclarationRecord, VisibilityProvenance], ...] = values
    if filters.defined_under is not None:
        try:
            under: str = normalize_path(path=filters.defined_under)
            selected = tuple(
                item
                for item in selected
                if is_equal_or_descendant(path=item[0].path, ancestor=under)
            )
        except InvalidScopePathError:
            selected = ()
    if filters.kinds:
        selected = tuple(item for item in selected if item[0].identity.kind in filters.kinds)
    if filters.glob is not None:
        selected = tuple(
            item
            for item in selected
            if fnmatchcase(item[0].identity.name, filters.glob)
            or fnmatchcase(format_identity(identity=item[0].identity), filters.glob)
        )
    if filters.used_only:
        selected = tuple(item for item in selected if item[0].identity in used_identities)
    return selected


def _filter_nearby(
    *,
    values: tuple[tuple[DeclarationRecord, str], ...],
    filters: ScopeReportFilters,
    used: set[DeclarationIdentity],
) -> tuple[tuple[DeclarationRecord, str], ...]:
    selected: tuple[tuple[DeclarationRecord, str], ...] = values
    if filters.defined_under is not None:
        try:
            under: str = normalize_path(path=filters.defined_under)
            selected = tuple(
                item
                for item in selected
                if is_equal_or_descendant(path=item[0].path, ancestor=under)
            )
        except InvalidScopePathError:
            selected = ()
    if filters.kinds:
        selected = tuple(item for item in selected if item[0].identity.kind in filters.kinds)
    if filters.glob is not None:
        selected = tuple(
            item
            for item in selected
            if fnmatchcase(item[0].identity.name, filters.glob)
            or fnmatchcase(format_identity(identity=item[0].identity), filters.glob)
        )
    if filters.used_only:
        selected = tuple(item for item in selected if item[0].identity in used)
    return selected


def _expand_dependencies(
    *,
    lookup: ScopeLookup,
    values: tuple[tuple[DeclarationRecord, VisibilityProvenance], ...],
    depth: int,
) -> tuple[tuple[DeclarationRecord, VisibilityProvenance], ...]:
    selected: dict[DeclarationIdentity, tuple[DeclarationRecord, VisibilityProvenance]] = {
        record.identity: (record, provenance) for record, provenance in values
    }
    frontier: set[DeclarationIdentity] = set(selected)
    for _level in range(max(depth, 0)):
        dependencies: set[DeclarationIdentity] = set()
        for identity in frontier:
            for record in lookup.declarations.get(identity, ()):
                if record.macro is not None:
                    dependencies.update(record.macro.dependencies)
            dependencies.update(
                usage.declaration for usage in lookup.usages_by_consumer.get(identity, ())
            )
        frontier = dependencies - set(selected)
        for identity in frontier:
            for record in lookup.declarations.get(identity, ()):
                selected[identity] = (record, VisibilityProvenance("dependency"))
    return tuple(
        sorted(
            selected.values(),
            key=lambda item: (format_identity(identity=item[0].identity), item[0].path),
        )
    )


def _nearby(
    *,
    lookup: ScopeLookup,
    resource: ResourceRecord,
    unavailable: tuple[tuple[DeclarationRecord, str], ...],
    depth: int,
) -> tuple[tuple[DeclarationRecord, str], ...]:
    parent: str = PurePosixPath(resource.path).parent.as_posix()
    parent_parts: tuple[str, ...] = PurePosixPath(parent).parts
    relationship_declarations: set[DeclarationIdentity] = {
        grant.declaration for grant in lookup.grants_by_resource.get(resource.identity, ())
    }
    result: list[tuple[DeclarationRecord, str]] = []
    for record, reason in unavailable:
        if record.scope is ScopeKind.PRIVATE and record.identity.owner != resource.identity:
            continue
        owner: str = record.owning_path or record.ownership_root.path
        owner_parts: tuple[str, ...] = PurePosixPath(owner).parts
        same_root: bool = record.ownership_root.path == resource.ownership_root.path
        ancestor: bool = is_equal_or_descendant(path=parent, ancestor=owner)
        connected: bool = record.identity in relationship_declarations
        sibling: bool = (
            max(depth, 0) >= 1 and PurePosixPath(owner).parent == PurePosixPath(parent).parent
        )
        descendant: bool = is_equal_or_descendant(path=owner, ancestor=parent) and (
            len(owner_parts) - len(parent_parts) <= max(depth, 0)
        )
        immediate_relative: bool = sibling or descendant
        if connected or (same_root and (ancestor or immediate_relative)):
            result.append((record, reason))
    return tuple(result)


def _scope_chain(*, lookup: ScopeLookup, resource: ResourceRecord) -> tuple[ScopeChainEntry, ...]:
    parent: str = PurePosixPath(resource.path).parent.as_posix()
    paths: set[str] = {parent}
    current: PurePosixPath = PurePosixPath(parent)
    while current.as_posix() not in {CURRENT_PATH_COMPONENT, resource.ownership_root.path}:
        current = current.parent
        paths.add(current.as_posix())
    paths.add(resource.ownership_root.path)
    entries: list[ScopeChainEntry] = []
    for path in sorted(paths, key=lambda item: (-len(PurePosixPath(item).parts), item)):
        count: int = sum(
            1
            for declaration in lookup.index.declarations
            if declaration.scope is not ScopeKind.GLOBAL
            and (declaration.owning_path or declaration.ownership_root.path) == path
        )
        entries.append(ScopeChainEntry("local" if path == parent else "inherited", path, count))
    global_count: int = sum(
        1 for declaration in lookup.index.declarations if declaration.scope is ScopeKind.GLOBAL
    )
    entries.append(ScopeChainEntry("global", "global", global_count))
    return tuple(entries)


def _resolve_cursor(
    *,
    requested: str | None,
    sections: tuple[tuple[tuple[DeclarationRecord, VisibilityProvenance], ...], ...],
) -> tuple[str | None, ScopeDiagnostic | None]:
    if requested is None:
        return None, None
    identities: tuple[str, ...] = _cursor_identities(sections=sections)
    unique_identities: set[str] = set(identities)
    section_match_counts: tuple[int, ...] = _section_identity_counts(
        sections=sections, identity=requested
    )
    if (
        QUALIFIED_IDENTITY_SEPARATOR in requested
        and requested in unique_identities
        and max(section_match_counts, default=0) == 1
    ):
        return requested, None
    bare_matches: tuple[str, ...] = tuple(
        identity
        for identity in sorted(unique_identities)
        if identity.rsplit(QUALIFIED_IDENTITY_SEPARATOR, 1)[-1] == requested
    )
    if QUALIFIED_IDENTITY_SEPARATOR not in requested and len(bare_matches) == 1:
        resolved: str = next(
            identity
            for identity in unique_identities
            if identity.rsplit(QUALIFIED_IDENTITY_SEPARATOR, 1)[-1] == requested
        )
        resolved_counts: tuple[int, ...] = _section_identity_counts(
            sections=sections, identity=resolved
        )
        if max(resolved_counts, default=0) == 1:
            return resolved, None
    diagnostic: ScopeDiagnostic = _diagnostic(
        code=ScopeDiagnosticCode.INVALID_CURSOR, value=requested
    )
    return None, diagnostic


def _page(
    *,
    lookup: ScopeLookup,
    name: str,
    values: tuple[tuple[DeclarationRecord, VisibilityProvenance], ...],
    cursor: str | None,
    page_size: int,
    complete: bool,
    collapsed: int = 0,
) -> tuple[tuple[DeclarationReport, ...], ScopeSection]:
    size: int = max(page_size, 0)
    start: int = 0
    if cursor is not None:
        start = next(
            (
                index + 1
                for index, item in enumerate(values)
                if format_identity(identity=item[0].identity) == cursor
            ),
            0,
        )
    selected: tuple[tuple[DeclarationRecord, VisibilityProvenance], ...] = values[
        start : start + size
    ]
    reports: tuple[DeclarationReport, ...] = tuple(
        declaration_report(lookup=lookup, record=record, visibility=provenance)
        for record, provenance in selected
    )
    truncated: bool = start + len(selected) < len(values)
    return reports, ScopeSection(
        name=name,
        total=len(values) + collapsed,
        returned=len(reports),
        collapsed=collapsed > 0,
        collapsed_count=collapsed,
        truncated=truncated,
        complete=complete,
        next_cursor=reports[-1].identity if reports and truncated else None,
        cursor=cursor,
        page_size=size,
    )


def _looks_like_path(*, value: str) -> bool:
    return (
        PATH_SEPARATOR in value
        or WINDOWS_PATH_SEPARATOR in value
        or PurePosixPath(value).suffix != EMPTY_TEXT
    )


def _ownership_roots(*, lookup: ScopeLookup) -> tuple[OwnershipRoot, ...]:
    roots: set[OwnershipRoot] = set(lookup.index.ownership_roots)
    roots.update(record.ownership_root for record in lookup.index.resources)
    return tuple(
        sorted(
            roots,
            key=lambda item: (
                -len(PurePosixPath(item.path).parts),
                item.path,
                item.resource_kind.value if item.resource_kind is not None else "",
            ),
        )
    )


def _resource_path_is_valid(*, path: str, root: OwnershipRoot) -> bool:
    if path == root.path:
        return False
    return PurePosixPath(path).suffix.lower() in _valid_suffixes(root=root)


def _default_suffix(*, root: OwnershipRoot) -> str:
    return ".yml" if root.resource_kind is ResourceKind.SOURCE else ".sql"


def _valid_suffixes(*, root: OwnershipRoot) -> frozenset[str]:
    if root.resource_kind is ResourceKind.SOURCE:
        return frozenset({".yml", ".yaml"})
    return frozenset({_default_suffix(root=root)})


def _declaration_pair_key[Provenance](
    item: tuple[DeclarationRecord, Provenance],
) -> tuple[str, str]:
    return format_identity(identity=item[0].identity), item[0].path


def _cursor_identities(
    *, sections: tuple[tuple[tuple[DeclarationRecord, VisibilityProvenance], ...], ...]
) -> tuple[str, ...]:
    identities: list[str] = []
    for section in sections:
        identities.extend(format_identity(identity=item[0].identity) for item in section)
    return tuple(identities)


def _section_identity_counts(
    *,
    sections: tuple[tuple[tuple[DeclarationRecord, VisibilityProvenance], ...], ...],
    identity: str,
) -> tuple[int, ...]:
    counts: list[int] = []
    for section in sections:
        count: int = sum(format_identity(identity=item[0].identity) == identity for item in section)
        counts.append(count)
    return tuple(counts)


def _diagnostic(*, code: ScopeDiagnosticCode, value: str) -> ScopeDiagnostic:
    label: str = "Target" if code is not ScopeDiagnosticCode.INVALID_CURSOR else "Cursor"
    return ScopeDiagnostic(code, f"{label} {value!r} is not valid for this scope query")


def _unknown_target_diagnostic(*, value: str) -> ScopeDiagnostic:
    target_type: str = "path" if _looks_like_path(value=value) else "qualified identity"
    return ScopeDiagnostic(
        ScopeDiagnosticCode.UNKNOWN_TARGET,
        f"Unknown {target_type} target {value!r}",
    )
