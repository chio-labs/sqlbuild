"""Immutable models for the canonical compiler scope index."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from sqlbuild.compiler.scopes.types import (
    CompletenessSection,
    DeclarationKind,
    DiagnosticSeverity,
    GrantKind,
    InaccessibleReason,
    OwnershipRootKind,
    ResourceKind,
    ScopeDiagnosticCode,
    ScopeKind,
    UsageKind,
    VisibilityReason,
)


@dataclass(frozen=True, order=True)
class ResourceIdentity:
    """Stable kind-qualified identity of one authored resource."""

    kind: ResourceKind
    name: str


@dataclass(frozen=True, order=True)
class DeclarationIdentity:
    """Stable declaration identity, including a private declaration owner."""

    kind: DeclarationKind
    name: str
    owner: ResourceIdentity | None = None


@dataclass(frozen=True, order=True)
class OwnershipRoot:
    """Normalized project-relative directory that owns resource scope."""

    path: str
    kind: OwnershipRootKind = OwnershipRootKind.RESOURCE
    resource_kind: ResourceKind | None = None


@dataclass(frozen=True)
class ResourceRecord:
    """One resource participating in lexical declaration scope."""

    identity: ResourceIdentity
    path: str
    ownership_root: OwnershipRoot


@dataclass(frozen=True)
class MacroMetadata:
    """Safe macro metadata required by scope and dependency inspection."""

    parameters: tuple[str, ...] = field(default_factory=tuple)
    dependencies: tuple[DeclarationIdentity, ...] = field(default_factory=tuple)
    source_digest: str = ""


@dataclass(frozen=True)
class EnumMemberMetadata:
    """One authored enum member and its normalized scalar value."""

    name: str
    value: str | int


@dataclass(frozen=True)
class EnumMetadata:
    """Safe enum metadata; members are names and normalized scalar values."""

    members: tuple[EnumMemberMetadata, ...]
    scalar_type: str


@dataclass(frozen=True)
class ConstantMetadata:
    """Value-free normalized metadata for one typed constant."""

    logical_type: str
    collection_kind: str | None = None
    item_count: int | None = None
    nullable: bool = False
    render_as: str | None = None


@dataclass(frozen=True)
class DeclarationRecord:
    """One declaration definition and its compiler-owned scope metadata."""

    identity: DeclarationIdentity
    path: str
    line: int
    column: int
    scope: ScopeKind
    ownership_root: OwnershipRoot
    owning_path: str | None = None
    macro: MacroMetadata | None = None
    enum: EnumMetadata | None = None
    constant: ConstantMetadata | None = None


@dataclass(frozen=True)
class UsageRecord:
    """A runtime or declaration dependency edge."""

    consumer: ResourceIdentity | DeclarationIdentity
    declaration: DeclarationIdentity
    kind: UsageKind = UsageKind.RUNTIME
    through: ResourceIdentity | None = None
    enum_member: str | None = None


@dataclass(frozen=True)
class GrantRecord:
    """A compiler relationship granting a public declaration to a resource."""

    resource: ResourceIdentity
    declaration: DeclarationIdentity
    through: ResourceIdentity
    kind: GrantKind = GrantKind.EXPECTED_MODEL


@dataclass(frozen=True)
class VisibilityRecord:
    """A resolved positive visibility fact with stable provenance."""

    resource: ResourceIdentity
    declaration: DeclarationIdentity
    reason: VisibilityReason
    through: ResourceIdentity | None = None


@dataclass(frozen=True)
class InaccessibleRecord:
    """A resolved negative visibility fact with stable provenance."""

    resource: ResourceIdentity
    declaration: DeclarationIdentity
    reason: InaccessibleReason


@dataclass(frozen=True)
class ScopeDiagnostic:
    """Stable diagnostic retained even when an index is partial."""

    code: ScopeDiagnosticCode
    message: str
    severity: DiagnosticSeverity = DiagnosticSeverity.ERROR
    path: str | None = None
    line: int | None = None
    column: int | None = None
    declaration: DeclarationIdentity | None = None
    resource: ResourceIdentity | None = None


@dataclass(frozen=True)
class ScopeCompleteness:
    """Independent completeness facts for partially invalid projects."""

    discovery: bool = True
    static_visibility: bool = True
    runtime_usage: bool = True
    relationships: bool = True
    placement: bool = True
    promotion_impact: bool = True

    @property
    def complete(self) -> bool:
        """Return whether every index section is complete."""

        return all(self.as_mapping().values())

    def as_mapping(self) -> Mapping[CompletenessSection, bool]:
        """Return immutable section completeness keyed by stable names."""

        return MappingProxyType(
            {
                CompletenessSection.DISCOVERY: self.discovery,
                CompletenessSection.STATIC_VISIBILITY: self.static_visibility,
                CompletenessSection.RUNTIME_USAGE: self.runtime_usage,
                CompletenessSection.RELATIONSHIPS: self.relationships,
                CompletenessSection.PLACEMENT: self.placement,
                CompletenessSection.PROMOTION_IMPACT: self.promotion_impact,
            }
        )


@dataclass(frozen=True)
class ScopeIndex:
    """Canonical deterministic facts used by every future scope consumer."""

    ownership_roots: tuple[OwnershipRoot, ...] = field(default_factory=tuple)
    resources: tuple[ResourceRecord, ...] = field(default_factory=tuple)
    declarations: tuple[DeclarationRecord, ...] = field(default_factory=tuple)
    usages: tuple[UsageRecord, ...] = field(default_factory=tuple)
    grants: tuple[GrantRecord, ...] = field(default_factory=tuple)
    visibility: tuple[VisibilityRecord, ...] = field(default_factory=tuple)
    inaccessible: tuple[InaccessibleRecord, ...] = field(default_factory=tuple)
    diagnostics: tuple[ScopeDiagnostic, ...] = field(default_factory=tuple)
    completeness: ScopeCompleteness = field(default_factory=ScopeCompleteness)


@dataclass(frozen=True)
class ScopeLookup:
    """Immutable indexes over one canonical ``ScopeIndex``."""

    index: ScopeIndex
    resources: Mapping[ResourceIdentity, tuple[ResourceRecord, ...]]
    resources_by_path: Mapping[str, tuple[ResourceRecord, ...]]
    declarations: Mapping[DeclarationIdentity, tuple[DeclarationRecord, ...]]
    usages_by_consumer: Mapping[ResourceIdentity | DeclarationIdentity, tuple[UsageRecord, ...]]
    usages_by_declaration: Mapping[DeclarationIdentity, tuple[UsageRecord, ...]]
    grants_by_resource: Mapping[ResourceIdentity, tuple[GrantRecord, ...]]
    visibility_by_resource: Mapping[ResourceIdentity, tuple[VisibilityRecord, ...]]
    inaccessible_by_resource: Mapping[ResourceIdentity, tuple[InaccessibleRecord, ...]]


@dataclass(frozen=True)
class ScopeTargetQuery:
    """Non-throwing qualified-identity or path lookup result."""

    value: str | ResourceIdentity | DeclarationIdentity
    matches: tuple[ResourceRecord, ...] = field(default_factory=tuple)
    declaration_matches: tuple[DeclarationRecord, ...] = field(default_factory=tuple)

    @property
    def unknown(self) -> bool:
        """Return whether the target is absent rather than merely inaccessible."""

        return not self.matches and not self.declaration_matches


@dataclass(frozen=True)
class VisibilityResolution:
    """Complete static visibility classification for one queried target."""

    target: ScopeTargetQuery
    visible: tuple[VisibilityRecord, ...] = field(default_factory=tuple)
    inaccessible: tuple[InaccessibleRecord, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ScopeReportFilters:
    """Orthogonal declaration filters applied in their documented fixed order."""

    sections: tuple[str, ...] = ("available", "used", "relationship_scope")
    include_nearby: bool = False
    defined_under: str | None = None
    kinds: tuple[DeclarationKind, ...] = field(default_factory=tuple)
    glob: str | None = None
    used_only: bool = False
    dependency_depth: int = 0
    sort: str = "identity"
    cursor: str | None = None
    page_size: int = 100
    nearby_depth: int = 1
    globals: str = "summary"


@dataclass(frozen=True)
class SourceLocation:
    """Safe project-relative source location."""

    path: str
    line: int
    column: int


@dataclass(frozen=True)
class VisibilityProvenance:
    """Why a declaration is visible or inaccessible."""

    reason: str
    through: str | None = None


@dataclass(frozen=True)
class DeclarationReport:
    """Value-free declaration projection used by every report section."""

    identity: str
    kind: str
    name: str
    owner: str | None
    definition: SourceLocation
    scope: str
    owning_path: str | None
    visibility: VisibilityProvenance | None = None
    inaccessible_reason: str | None = None
    metadata: tuple[tuple[str, object], ...] = field(default_factory=tuple)
    consumers: tuple[str, ...] = field(default_factory=tuple)
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    grants: tuple[str, ...] = field(default_factory=tuple)
    required_scope: str | None = None
    required_path: str | None = None
    promotion_impact: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ScopeChainEntry:
    """One exact or inherited lexical scope in deterministic path order."""

    kind: str
    path: str
    declaration_count: int


@dataclass(frozen=True)
class ScopeSection:
    """Pagination and completeness metadata for one report section."""

    name: str
    total: int
    returned: int
    collapsed: bool = False
    collapsed_count: int = 0
    truncated: bool = False
    complete: bool = True
    next_cursor: str | None = None
    cursor: str | None = None
    page_size: int = 100


@dataclass(frozen=True)
class ScopeResourceReport:
    """Resolved existing resource or prospective authored path."""

    target: str
    identity: str | None
    path: str | None
    prospective: bool = False
    directory: bool = False
    duplicate_count: int = 0


@dataclass(frozen=True)
class DeclarationExplanation:
    """Detailed explanation for one qualified declaration."""

    declaration: DeclarationReport | None
    complete: bool


@dataclass(frozen=True)
class MovePreview:
    """Pure visibility delta for moving one existing resource."""

    resource: str
    destination: str
    new_ownership_root: str | None
    retained: tuple[DeclarationReport, ...] = field(default_factory=tuple)
    gained: tuple[DeclarationReport, ...] = field(default_factory=tuple)
    lost: tuple[DeclarationReport, ...] = field(default_factory=tuple)
    invalidated_usages: tuple[str, ...] = field(default_factory=tuple)
    private_retained: tuple[DeclarationReport, ...] = field(default_factory=tuple)
    relationship_retained: tuple[DeclarationReport, ...] = field(default_factory=tuple)
    complete: bool = True


@dataclass(frozen=True)
class ScopeFolder:
    """One declaration-definition folder with exact recursive counts."""

    path: str
    name: str
    descendant_count: int
    child_count: int
    used_count: int
    kind_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class ScopeBrowseResult:
    """Folder-first browse result."""

    folder: str
    folders: tuple[ScopeFolder, ...]
    diagnostics: tuple[ScopeDiagnostic, ...] = field(default_factory=tuple)
    complete: bool = True


@dataclass(frozen=True)
class ScopeListResult:
    """Recursive declaration list beneath one definition folder."""

    folder: str
    declarations: tuple[DeclarationReport, ...]
    section: ScopeSection
    diagnostics: tuple[ScopeDiagnostic, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ScopeReport:
    """Canonical payload shared by all non-rendering scope consumers."""

    resource: ScopeResourceReport
    scope_chain: tuple[ScopeChainEntry, ...] = field(default_factory=tuple)
    available: tuple[DeclarationReport, ...] = field(default_factory=tuple)
    used: tuple[DeclarationReport, ...] = field(default_factory=tuple)
    relationship_scope: tuple[DeclarationReport, ...] = field(default_factory=tuple)
    nearby_unavailable: tuple[DeclarationReport, ...] = field(default_factory=tuple)
    filters: ScopeReportFilters = field(default_factory=ScopeReportFilters)
    sections: tuple[ScopeSection, ...] = field(default_factory=tuple)
    explanation: DeclarationExplanation | None = None
    move_preview: MovePreview | None = None
    diagnostics: tuple[ScopeDiagnostic, ...] = field(default_factory=tuple)
    complete: bool = True
