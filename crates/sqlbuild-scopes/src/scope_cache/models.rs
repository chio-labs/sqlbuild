//! A full scope index as the cache stores it, and the fingerprint's inputs and outcome.

use crate::scope_index::models::{
    DeclarationIdentity, DeclarationRecord, OwnershipRoot, QualifiedIdentity, ReportGrant,
    ResourceIdentity, ResourceRecord,
};

/// A macro declaration's parameters, dependencies and source digest.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct MacroFacts {
    pub parameters: Vec<String>,
    pub dependencies: Vec<DeclarationIdentity>,
    pub source_digest: String,
}

/// An enum declaration's member names and scalar type.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct EnumFacts {
    pub members: Vec<String>,
    pub scalar_type: String,
}

/// A constant declaration's value-free shape.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ConstantFacts {
    pub logical_type: String,
    pub collection_kind: Option<String>,
    pub item_count: Option<i64>,
    pub nullable: bool,
    pub render_as: Option<String>,
}

/// A declaration record with its value metadata.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CachedDeclaration {
    pub record: DeclarationRecord,
    pub macro_facts: Option<MacroFacts>,
    pub enum_facts: Option<EnumFacts>,
    pub constant_facts: Option<ConstantFacts>,
}

/// One usage with its kind text and the enum member it reads.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CachedUsage {
    pub consumer: QualifiedIdentity,
    pub declaration: DeclarationIdentity,
    pub kind: String,
    pub through: Option<QualifiedIdentity>,
    pub enum_member: Option<String>,
}

/// One precomputed visibility fact with its reason text.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CachedVisibility {
    pub resource: ResourceIdentity,
    pub declaration: DeclarationIdentity,
    pub reason: String,
    pub through: Option<QualifiedIdentity>,
}

/// One precomputed inaccessible fact with its reason text.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CachedInaccessible {
    pub resource: ResourceIdentity,
    pub declaration: DeclarationIdentity,
    pub reason: String,
}

/// One scope diagnostic with its code and severity text.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CachedDiagnostic {
    pub code: String,
    pub message: String,
    pub severity: String,
    pub path: Option<String>,
    pub line: Option<i64>,
    pub column: Option<i64>,
    pub declaration: Option<DeclarationIdentity>,
    pub resource: Option<ResourceIdentity>,
}

/// Python's `ScopeIndex` with every field the cache stores.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct CachedIndex {
    pub roots: Vec<OwnershipRoot>,
    pub resources: Vec<ResourceRecord>,
    pub declarations: Vec<CachedDeclaration>,
    pub usages: Vec<CachedUsage>,
    pub grants: Vec<ReportGrant>,
    pub visibility: Vec<CachedVisibility>,
    pub inaccessible: Vec<CachedInaccessible>,
    pub diagnostics: Vec<CachedDiagnostic>,
    /// Discovery, static visibility, runtime usage, relationships, placement, promotion impact.
    pub completeness: [bool; 6],
}

/// What the fingerprint reads besides the project's files.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FingerprintInputs {
    /// Config files hashed when present, in order.
    pub config_files: Vec<String>,
    /// Every candidate source root; the fingerprint hashes their sorted distinct set.
    pub roots: Vec<String>,
    /// Folder names that make any file below them a declaration source.
    pub declaration_directories: Vec<String>,
    /// First-level folders whose files are named declaration sources.
    pub named_declaration_directories: Vec<String>,
    pub sqlbuild_version: String,
}

/// The fingerprint, or why Python would have no fingerprint or raise.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Fingerprint {
    Hash(String),
    /// An I/O, decoding or value fault: Python's caught `OSError`, `UnicodeError` or `ValueError`.
    Unavailable,
    /// A config value `json.dumps` cannot serialize: Python's uncaught `TypeError`.
    Unserializable,
}

/// Why a cache file is a miss.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CacheMiss {
    /// Unreadable, oversized or not JSON.
    Unreadable,
    /// The envelope's schema, fingerprint or payload digest does not match.
    Stale,
    /// The payload fails Python's decoder.
    Invalid,
}

/// Why a full index has no cache envelope: Python skips the write.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Unencodable;
