//! Report facts, requests and the report results Python's scope report models mirror.

use sqlbuild_core::json::models::JsonValue;

use crate::scope_index::models::{
    DeclarationIdentity, DeclarationRecord, GrantKind, IdentityFailure, OwnershipRoot,
    QualifiedIdentity, RejectedPath, ReportLookup, ReportRecords, ResourceIdentity, ResourceRecord,
};

/// Python's `MacroMetadata`.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct MacroValues {
    pub parameters: Vec<String>,
    pub dependencies: Vec<DeclarationIdentity>,
    pub source_digest: String,
}

/// Python's `EnumMetadata`: member names and the scalar type.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct EnumValues {
    pub members: Vec<String>,
    pub scalar_type: String,
}

/// Python's `ConstantMetadata`.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ConstantValues {
    pub logical_type: String,
    pub collection_kind: Option<String>,
    pub item_count: Option<i64>,
    pub nullable: bool,
    pub render_as: Option<String>,
}

/// One declaration's value metadata.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DeclarationValues {
    pub macro_values: Option<MacroValues>,
    pub enum_values: Option<EnumValues>,
    pub constant_values: Option<ConstantValues>,
}

/// Python's `ScopeCompleteness`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Completeness {
    pub discovery: bool,
    pub static_visibility: bool,
    pub runtime_usage: bool,
    pub relationships: bool,
    pub placement: bool,
    pub promotion_impact: bool,
}

impl Default for Completeness {
    fn default() -> Self {
        Self {
            discovery: true,
            static_visibility: true,
            runtime_usage: true,
            relationships: true,
            placement: true,
            promotion_impact: true,
        }
    }
}

/// What reports read beside the lookup: each record's value metadata, in input order.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ReportValues {
    pub declarations: Vec<DeclarationValues>,
    pub completeness: Completeness,
}

/// A lookup's records and groups with the values reports read.
#[derive(Clone, Copy, Debug)]
pub struct ReportSource<'a> {
    pub records: &'a ReportRecords,
    pub lookup: &'a ReportLookup,
    pub values: &'a ReportValues,
}

/// What a query names: an identity, text naming an identity or path, or a `PurePath`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum QueryTarget {
    Identity(QualifiedIdentity),
    Text(String),
    /// A `PurePath`, which reads as path text without the text-only identity checks.
    Path(String),
}

/// Python's `ScopeReportFilters`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ReportFilters {
    pub sections: Vec<String>,
    pub include_nearby: bool,
    pub defined_under: Option<String>,
    /// Declaration kind values.
    pub kinds: Vec<String>,
    pub glob: Option<String>,
    pub used_only: bool,
    pub dependency_depth: i64,
    pub sort: String,
    pub cursor: Option<String>,
    pub page_size: i64,
    pub nearby_depth: i64,
    pub globals: String,
}

/// `query_scope_report`'s arguments.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ReportRequest {
    pub target: Option<QueryTarget>,
    pub at: Option<String>,
    pub directory: bool,
    pub filters: ReportFilters,
}

/// A declaration to explain: an identity, or text naming one.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum DeclarationTarget {
    Identity(DeclarationIdentity),
    Text(String),
}

/// `explain_scope_declaration`'s arguments.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ExplainRequest {
    pub declaration: DeclarationTarget,
    pub target: Option<QueryTarget>,
    pub at: Option<String>,
    pub directory: bool,
}

/// `browse_scope_folders` and `list_scope_declarations` arguments.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FolderRequest {
    pub folder: String,
    pub target: Option<QueryTarget>,
    pub prospective: bool,
    /// The list filters; `None` lists everything with every global.
    pub filters: Option<ReportFilters>,
}

/// `preview_scope_move`'s arguments; `destination` is `str(destination)`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct MoveRequest {
    pub resource: QueryTarget,
    pub destination: String,
}

/// Python's `ScopeDiagnostic` as a report projects it: identities as qualified text.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DiagnosticFacts {
    pub code: String,
    pub message: String,
    pub severity: String,
    pub path: Option<String>,
    pub line: Option<i64>,
    pub column: Option<i64>,
    pub declaration: Option<String>,
    pub resource: Option<String>,
}

/// A report diagnostic: the index diagnostic at a canonical position, or one the query raised.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ReportDiagnostic {
    Index(usize),
    Raised(DiagnosticFacts),
}

/// Python's `VisibilityProvenance`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Provenance {
    pub reason: String,
    pub through: Option<String>,
}

/// Python's `SourceLocation`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SourceLocation {
    pub path: String,
    pub line: i64,
    pub column: i64,
}

/// Python's `DeclarationReport`; metadata values are JSON-ready, arrays standing for tuples.
#[derive(Clone, Debug, PartialEq)]
pub struct DeclarationReport {
    pub identity: String,
    pub kind: String,
    pub name: String,
    pub owner: Option<String>,
    pub definition: SourceLocation,
    pub scope: String,
    pub owning_path: Option<String>,
    pub visibility: Option<Provenance>,
    pub inaccessible_reason: Option<String>,
    pub metadata: Vec<(String, JsonValue)>,
    pub consumers: Vec<String>,
    pub dependencies: Vec<String>,
    pub grants: Vec<String>,
    pub required_scope: Option<String>,
    pub required_path: Option<String>,
    pub promotion_impact: Vec<String>,
}

/// Python's `ScopeChainEntry`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ScopeChainEntry {
    pub kind: String,
    pub path: String,
    pub declaration_count: i64,
}

/// Python's `ScopeSection`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ScopeSection {
    pub name: String,
    pub total: i64,
    pub returned: i64,
    pub collapsed: bool,
    pub collapsed_count: i64,
    pub truncated: bool,
    pub complete: bool,
    pub next_cursor: Option<String>,
    pub cursor: Option<String>,
    pub page_size: i64,
}

/// Python's `ScopeResourceReport`.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ResourceReport {
    pub target: String,
    pub identity: Option<String>,
    pub path: Option<String>,
    pub prospective: bool,
    pub directory: bool,
    pub duplicate_count: i64,
}

/// Python's `DeclarationExplanation`.
#[derive(Clone, Debug, PartialEq)]
pub struct Explanation {
    pub declaration: Option<DeclarationReport>,
    pub complete: bool,
}

/// Python's `MovePreview`.
#[derive(Clone, Debug, PartialEq)]
pub struct MovePreview {
    pub resource: String,
    pub destination: String,
    pub new_ownership_root: Option<String>,
    pub retained: Vec<DeclarationReport>,
    pub gained: Vec<DeclarationReport>,
    pub lost: Vec<DeclarationReport>,
    pub invalidated_usages: Vec<String>,
    pub private_retained: Vec<DeclarationReport>,
    pub relationship_retained: Vec<DeclarationReport>,
    pub complete: bool,
}

/// Python's `ScopeFolder`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ScopeFolder {
    pub path: String,
    pub name: String,
    pub descendant_count: i64,
    pub child_count: i64,
    pub used_count: i64,
    pub kind_counts: Vec<(String, i64)>,
}

/// Python's `ScopeReport`.
#[derive(Clone, Debug, PartialEq)]
pub struct ScopeReport {
    pub resource: ResourceReport,
    pub scope_chain: Vec<ScopeChainEntry>,
    pub available: Vec<DeclarationReport>,
    pub used: Vec<DeclarationReport>,
    pub relationship_scope: Vec<DeclarationReport>,
    pub nearby_unavailable: Vec<DeclarationReport>,
    pub filters: ReportFilters,
    pub sections: Vec<ScopeSection>,
    pub explanation: Option<Explanation>,
    pub move_preview: Option<MovePreview>,
    pub diagnostics: Vec<ReportDiagnostic>,
    pub complete: bool,
}

/// Python's `ScopeBrowseResult`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct BrowseResult {
    pub folder: String,
    pub folders: Vec<ScopeFolder>,
    pub diagnostics: Vec<ReportDiagnostic>,
    pub complete: bool,
}

/// Python's `ScopeListResult`.
#[derive(Clone, Debug, PartialEq)]
pub struct ListResult {
    pub folder: String,
    pub declarations: Vec<DeclarationReport>,
    pub section: ScopeSection,
    pub diagnostics: Vec<ReportDiagnostic>,
}

/// Any scope query result `serialize_scope_report` accepts.
#[derive(Clone, Debug, PartialEq)]
pub enum ScopeResult {
    Report(Box<ScopeReport>),
    Browse(BrowseResult),
    List(ListResult),
}

/// Why a query raises: a path `normalize_path` rejects, or an identity `parse_identity` rejects.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ReportFailure {
    Path(RejectedPath),
    /// The failure and the text Python parsed.
    Identity(IdentityFailure, String),
    /// Serialization met an index diagnostic it cannot project or a value JSON cannot hold.
    Serialization(String),
    /// An input Python's report code reads past an empty result for, raising `IndexError`.
    IndexOutOfRange,
}

/// One usage of a full scope index, with the enum member the metadata projection shows.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ProjectionUsage {
    pub consumer: QualifiedIdentity,
    pub declaration: DeclarationIdentity,
    pub kind: String,
    pub through: Option<QualifiedIdentity>,
    pub enum_member: Option<String>,
}

/// One relationship grant of a full scope index.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ProjectionGrant {
    pub resource: ResourceIdentity,
    pub declaration: DeclarationIdentity,
    pub through: QualifiedIdentity,
    pub kind: GrantKind,
}

/// A stored visible or inaccessible fact: resource, declaration, reason and what it came through.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ProjectionStanding {
    pub resource: ResourceIdentity,
    pub declaration: DeclarationIdentity,
    pub reason: String,
    pub through: Option<QualifiedIdentity>,
}

/// A full `ScopeIndex` in its tuple orders, for `scope_metadata_projection`.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ProjectionIndex {
    pub roots: Vec<OwnershipRoot>,
    pub resources: Vec<ResourceRecord>,
    pub declarations: Vec<DeclarationRecord>,
    pub values: ReportValues,
    pub usages: Vec<ProjectionUsage>,
    pub grants: Vec<ProjectionGrant>,
    pub visibility: Vec<ProjectionStanding>,
    pub inaccessible: Vec<ProjectionStanding>,
    pub diagnostics: Vec<DiagnosticFacts>,
}
