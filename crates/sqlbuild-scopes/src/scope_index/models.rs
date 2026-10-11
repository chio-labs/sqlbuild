//! Scope enums, inputs, records and lookup groups exchanged with the Python scope facade.

use std::collections::HashMap;

/// Python's `ResourceKind`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum ResourceKind {
    Model,
    Test,
    Scenario,
    Function,
    Source,
    Seed,
}

impl ResourceKind {
    /// Python's enum value.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Model => "model",
            Self::Test => "test",
            Self::Scenario => "scenario",
            Self::Function => "function",
            Self::Source => "source",
            Self::Seed => "seed",
        }
    }

    /// Python's enum member name, as `repr` prints it.
    pub fn member_name(self) -> &'static str {
        match self {
            Self::Model => "MODEL",
            Self::Test => "TEST",
            Self::Scenario => "SCENARIO",
            Self::Function => "FUNCTION",
            Self::Source => "SOURCE",
            Self::Seed => "SEED",
        }
    }

    /// The kind with Python's enum value `value`.
    pub fn parse(value: &str) -> Option<Self> {
        [
            Self::Model,
            Self::Test,
            Self::Scenario,
            Self::Function,
            Self::Source,
            Self::Seed,
        ]
        .into_iter()
        .find(|kind| kind.as_str() == value)
    }
}

/// Python's `DeclarationKind`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum DeclarationKind {
    Macro,
    Enum,
    Constant,
    Audit,
    SingularAudit,
    Schema,
    SqlHook,
    PythonHook,
}

impl DeclarationKind {
    /// Python's enum value.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Macro => "macro",
            Self::Enum => "enum",
            Self::Constant => "constant",
            Self::Audit => "audit",
            Self::SingularAudit => "singular_audit",
            Self::Schema => "schema",
            Self::SqlHook => "sql_hook",
            Self::PythonHook => "python_hook",
        }
    }

    /// Python's enum member name, as `repr` prints it.
    pub fn member_name(self) -> &'static str {
        match self {
            Self::Macro => "MACRO",
            Self::Enum => "ENUM",
            Self::Constant => "CONSTANT",
            Self::Audit => "AUDIT",
            Self::SingularAudit => "SINGULAR_AUDIT",
            Self::Schema => "SCHEMA",
            Self::SqlHook => "SQL_HOOK",
            Self::PythonHook => "PYTHON_HOOK",
        }
    }

    /// Python's `DECLARATION_ROLE_PARTS`: the folders a declaration of this kind lives under.
    pub fn role_parts(self) -> &'static [&'static str] {
        match self {
            Self::Macro => &["macros"],
            Self::Enum => &["enums"],
            Self::Constant => &["constants"],
            Self::Audit => &["audits", "generic"],
            Self::SingularAudit => &["audits", "singular"],
            Self::Schema => &["schemas"],
            Self::SqlHook => &["hooks", "sql"],
            Self::PythonHook => &["hooks", "python"],
        }
    }

    /// The kind with Python's enum value `value`.
    pub fn parse(value: &str) -> Option<Self> {
        [
            Self::Macro,
            Self::Enum,
            Self::Constant,
            Self::Audit,
            Self::SingularAudit,
            Self::Schema,
            Self::SqlHook,
            Self::PythonHook,
        ]
        .into_iter()
        .find(|kind| kind.as_str() == value)
    }
}

/// Python's `ScopeKind`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum ScopeKind {
    Global,
    Inherited,
    Local,
    Private,
}

impl ScopeKind {
    /// Python's enum value.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Global => "global",
            Self::Inherited => "inherited",
            Self::Local => "local",
            Self::Private => "private",
        }
    }

    /// The scope with Python's enum value `value`.
    pub fn parse(value: &str) -> Option<Self> {
        [Self::Global, Self::Inherited, Self::Local, Self::Private]
            .into_iter()
            .find(|scope| scope.as_str() == value)
    }
}

/// Python's `OwnershipRootKind`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum OwnershipRootKind {
    Resource,
    Global,
}

impl OwnershipRootKind {
    /// Python's enum value.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Resource => "resource",
            Self::Global => "global",
        }
    }

    /// The kind with Python's enum `value`.
    pub fn parse(value: &str) -> Option<Self> {
        [Self::Resource, Self::Global]
            .into_iter()
            .find(|kind| kind.as_str() == value)
    }
}

/// Python's `GrantKind`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum GrantKind {
    ExpectedModel,
    TestedMacro,
}

impl GrantKind {
    /// Python's enum value.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::ExpectedModel => "expected_model",
            Self::TestedMacro => "tested_macro",
        }
    }
}

/// The `ScopeDiagnosticCode`s the static index builder reports.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum ScopeDiagnosticCode {
    DuplicateDeclaration,
    InvalidDeclarationName,
    ReservedDeclarationName,
    DuplicateResource,
}

impl ScopeDiagnosticCode {
    /// Python's enum value.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::DuplicateDeclaration => "S003",
            Self::InvalidDeclarationName => "S004",
            Self::ReservedDeclarationName => "S005",
            Self::DuplicateResource => "S018",
        }
    }
}

/// Which ownership root an authored resource belongs to.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ResourceRoot {
    /// The resource kind's own root, such as `models` or `tests/unit`.
    Kind,
    /// The global `seeds` root.
    Seed,
    /// The global `functions/python` root.
    PythonFunction,
}

/// Python's `ResourceIdentity`.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct ResourceIdentity {
    pub kind: ResourceKind,
    pub name: String,
}

/// Python's `DeclarationIdentity`.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct DeclarationIdentity {
    pub kind: DeclarationKind,
    pub name: String,
    pub owner: Option<ResourceIdentity>,
}

/// Python's `OwnershipRoot`.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct OwnershipRoot {
    pub path: String,
    pub kind: OwnershipRootKind,
    pub resource_kind: Option<ResourceKind>,
}

/// One authored resource as the Python builder walks it, with its path as `str(Path)` prints it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ResourceInput {
    pub identity: ResourceIdentity,
    pub path: String,
    pub root: ResourceRoot,
}

/// One declaration as the Python builder walks it, with paths as `str(Path)` prints them.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DeclarationInput {
    pub identity: DeclarationIdentity,
    pub path: String,
    pub line: i64,
    pub scope: ScopeKind,
    /// The discovered ownership root, when discovery recorded one.
    pub ownership_root: Option<String>,
    /// The global root used without a discovered ownership root.
    pub root_fallback: String,
    pub owning_path: Option<String>,
    /// A loaded macro's declaration dependencies; empty for every other declaration.
    pub dependencies: Vec<DeclarationIdentity>,
}

/// The builder's inputs in Python's walk order: resources, then declarations.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ScopeInputs {
    pub resources: Vec<ResourceInput>,
    pub declarations: Vec<DeclarationInput>,
}

/// Python's `ResourceRecord`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ResourceRecord {
    pub identity: ResourceIdentity,
    pub path: String,
    pub ownership_root: OwnershipRoot,
}

/// Python's `DeclarationRecord` without its value metadata, which the facade keeps.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DeclarationRecord {
    pub identity: DeclarationIdentity,
    pub path: String,
    pub line: i64,
    pub column: i64,
    pub scope: ScopeKind,
    pub ownership_root: OwnershipRoot,
    pub owning_path: Option<String>,
    pub dependencies: Vec<DeclarationIdentity>,
}

/// A macro declaration dependency: `declarations[consumer].dependencies[dependency]`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct UsageRecord {
    pub consumer: usize,
    pub dependency: usize,
}

/// Python's `ScopeDiagnostic`; `declaration` and `resource` index the index's records.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ScopeDiagnostic {
    pub code: ScopeDiagnosticCode,
    pub message: String,
    pub path: Option<String>,
    pub line: Option<i64>,
    pub column: Option<i64>,
    pub declaration: Option<usize>,
    pub resource: Option<usize>,
}

/// The static scope index with every ordering the Python builder and lookup produce.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ScopeIndex {
    /// Resource records in input order.
    pub resources: Vec<ResourceRecord>,
    /// Declaration records in input order.
    pub declarations: Vec<DeclarationRecord>,
    /// The builder's `ScopeIndex.resources` order.
    pub resource_order: Vec<usize>,
    /// The builder's `ScopeIndex.declarations` order.
    pub declaration_order: Vec<usize>,
    /// The lookup's canonical resource order.
    pub canonical_resources: Vec<usize>,
    /// The lookup's canonical declaration order; visibility positions index this list.
    pub canonical_declarations: Vec<usize>,
    /// The builder's deduplicated macro dependency usages.
    pub usages: Vec<UsageRecord>,
    /// The builder's sorted diagnostics.
    pub diagnostics: Vec<ScopeDiagnostic>,
    /// Whether any macro, enum or constant is scoped, which makes relationship grants matter.
    pub has_scoped_relationship_declarations: bool,
}

/// The relationship facts the Python facade extracted for one test block or scenario.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RelationshipFact {
    pub resource: ResourceIdentity,
    /// `__expected__<model>` names in authored order.
    pub expected_models: Vec<String>,
    /// Macro names the block calls, including nested calls; empty for scenarios.
    pub called_macros: Vec<String>,
    /// Macros called in a macro test's `__actual__` CTE, in encounter order.
    pub tested_macros: Vec<String>,
}

/// What a grant came through: an expected model, or a tested macro declaration.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub enum GrantThrough {
    Model(String),
    Declaration(usize),
}

/// Python's `GrantRecord`; `declaration` indexes the index's declaration records.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct GrantRecord {
    pub resource: ResourceIdentity,
    pub declaration: usize,
    pub through: GrantThrough,
    pub kind: GrantKind,
}

/// One lookup mapping's groups; members index the records the mapping groups.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct KeyedGroups {
    /// Groups in Python's `repr(key)` order.
    pub groups: Vec<Vec<usize>>,
}

/// Python's `DeclarationVisibilityIndex` positions over the canonical declarations.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct VisibilityGroups {
    pub global: Vec<usize>,
    /// Private positions per owner, in first-occurrence order.
    pub private: Vec<(ResourceIdentity, Vec<usize>)>,
    pub local: Vec<(String, Vec<usize>)>,
    pub inherited: Vec<(String, Vec<usize>)>,
}

/// The native scope stage cannot reproduce Python for this project; the Python stage runs instead.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ScopeDeferral {
    pub reason: String,
}

/// Python's `VisibilityReason`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum VisibilityReason {
    Global,
    InheritedAncestor,
    LocalOwner,
    PrivateOwner,
    ExpectedModel,
    TestedMacro,
}

impl VisibilityReason {
    /// Python's enum value text.
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Global => "global",
            Self::InheritedAncestor => "inherited_ancestor",
            Self::LocalOwner => "local_owner",
            Self::PrivateOwner => "private_owner",
            Self::ExpectedModel => "expected_model",
            Self::TestedMacro => "tested_macro",
        }
    }
}

/// Python's `DeclarationVisibilityIndex` without its private owners, which callers resolve.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct VisibilityTable {
    /// One key per canonical declaration position; equal keys mean equal identities.
    pub identity_keys: Vec<u32>,
    pub global: Vec<usize>,
    pub local: HashMap<String, Vec<usize>>,
    pub inherited: HashMap<String, Vec<usize>>,
}

/// One relationship grant: the declaration it opens, why, and the caller's `through` slot.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct GrantEntry {
    pub identity_key: u32,
    pub reason: VisibilityReason,
    pub through: usize,
}

/// One resource matching the consumer: its private positions, authored path and grants.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ConsumerResource {
    pub private: Vec<usize>,
    pub path: String,
    pub grants: Vec<GrantEntry>,
}

/// One visible fact: a declaration position, the reason, and the grant's `through` slot.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct VisibleEntry {
    pub position: usize,
    pub reason: VisibilityReason,
    pub through: Option<usize>,
}

/// What one matching resource can see, in Python's record order, and what stays inaccessible.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ResourceVisibility {
    pub visible: Vec<VisibleEntry>,
    pub inaccessible: Vec<usize>,
}

/// The scope facts that decide whether a declaration is visible from an authored path.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DeclaredScope {
    pub scope: ScopeKind,
    /// The owning resource of a private declaration.
    pub owner: Option<ResourceIdentity>,
    pub owning_path: Option<String>,
}

/// A qualified identity as Python's `parse_identity` reads it.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub enum QualifiedIdentity {
    Resource(ResourceIdentity),
    Declaration(DeclarationIdentity),
}

/// Why Python's `parse_identity` rejects a value; each names the value or the raw kind.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum IdentityFailure {
    /// `Qualified identity has no name: {value!r}`.
    NoName,
    /// `Unknown qualified identity kind: {raw_kind!r}`.
    UnknownKind(String),
    /// `Invalid private identity: {value!r}`.
    InvalidPrivate,
    /// `Expected a kind-qualified identity such as 'model:name': {value!r}`.
    Unqualified,
}

/// Why Python's `normalize_path` raises `InvalidScopePathError`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ScopePathFailure {
    /// `Scope path must be project-relative: {path}`.
    NotProjectRelative,
    /// `Scope path escapes the project: {path}`.
    EscapesProject,
}

/// One usage of a full scope index: consumer, declaration, usage kind and what it came through.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ReportUsage {
    pub consumer: QualifiedIdentity,
    pub declaration: DeclarationIdentity,
    pub kind: String,
    pub through: Option<QualifiedIdentity>,
}

/// One relationship grant of a full scope index.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ReportGrant {
    pub resource: ResourceIdentity,
    pub declaration: DeclarationIdentity,
    pub through: QualifiedIdentity,
    pub kind: GrantKind,
}

/// The parts of a diagnostic the lookup orders diagnostics by.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ReportDiagnosticKey {
    pub path: Option<String>,
    pub line: Option<i64>,
    pub column: Option<i64>,
    pub code: String,
}

/// A full scope index's records as Python's `ScopeIndex` holds them, in its tuple orders.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ReportRecords {
    pub roots: Vec<OwnershipRoot>,
    pub resources: Vec<ResourceRecord>,
    pub declarations: Vec<DeclarationRecord>,
    pub usages: Vec<ReportUsage>,
    pub grants: Vec<ReportGrant>,
    pub diagnostics: Vec<ReportDiagnosticKey>,
}

/// Python's `build_lookup` over report records: canonical orders, groups and visibility.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ReportLookup {
    pub roots: Vec<usize>,
    pub resources: Vec<usize>,
    pub declarations: Vec<usize>,
    pub usages: Vec<usize>,
    pub grants: Vec<usize>,
    pub diagnostics: Vec<usize>,
    pub groups: ReportGroups,
    pub visibility: VisibilityGroups,
    /// Each input resource's normalized path, the `resources_by_path` key.
    pub resource_paths: Vec<String>,
}

/// The lookup's mappings as groups of record positions.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ReportGroups {
    pub resources: KeyedGroups,
    pub resources_by_path: KeyedGroups,
    pub declarations: KeyedGroups,
    pub usages_by_consumer: KeyedGroups,
    pub usages_by_declaration: KeyedGroups,
    pub grants_by_resource: KeyedGroups,
}

/// A path Python's `normalize_path` rejects, and why.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RejectedPath {
    pub failure: ScopePathFailure,
    pub path: String,
}

/// What a scope query targets: an identity, or text naming one or a resource path.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ReportTarget {
    Identity(QualifiedIdentity),
    Text(String),
}

/// Python's `ScopeTargetQuery` matches as record positions in lookup group order.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum TargetMatch {
    Resources(Vec<usize>),
    Declarations(Vec<usize>),
}

/// Why Python's `query_target` raises.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum TargetFailure {
    Identity(IdentityFailure),
    Path(RejectedPath),
}

/// Python's `InaccessibleReason`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum InaccessibleReason {
    LocalBoundary,
    SiblingScope,
    DescendantScope,
    UnrelatedScope,
    PrivateOwner,
}

impl InaccessibleReason {
    /// Python's enum value text.
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::LocalBoundary => "local_boundary",
            Self::SiblingScope => "sibling_scope",
            Self::DescendantScope => "descendant_scope",
            Self::UnrelatedScope => "unrelated_scope",
            Self::PrivateOwner => "private_owner",
        }
    }
}

/// One relationship-visible declaration: its position, reason and sorted `through` text.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RelationshipEntry {
    pub position: usize,
    pub reason: VisibilityReason,
    pub through: String,
}

/// The report's `_classify`: direct, relationship and unavailable declarations, each sorted.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ReportClassification {
    pub direct: Vec<(usize, VisibilityReason)>,
    pub relationships: Vec<RelationshipEntry>,
    pub unavailable: Vec<(usize, InaccessibleReason)>,
}

/// One visible fact: a canonical declaration position, the reason, and the granting grant.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ResolvedVisible {
    pub position: usize,
    pub reason: VisibilityReason,
    pub grant: Option<usize>,
}

/// Python's `_classify_resource` with each inaccessible position's reason.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ResolvedVisibility {
    pub visible: Vec<ResolvedVisible>,
    pub inaccessible: Vec<(usize, InaccessibleReason)>,
}

/// How one declaration stands for a resource in a scope explanation.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum DeclarationStanding {
    Visible(VisibilityReason),
    /// Granted by relationships: the reason and the sorted `through` identities joined by commas.
    Granted(VisibilityReason, String),
    Inaccessible(InaccessibleReason),
}
