//! The scope facts placement rules read and the placements and diagnostics they derive.

use crate::scope_index::models::{
    DeclarationIdentity, DeclarationRecord, OwnershipRoot, QualifiedIdentity, ResourceRecord,
    ScopeKind,
};

/// Python's `UsageRecord`, without the kind and enum member placement ignores.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct PlacementUsage {
    pub consumer: QualifiedIdentity,
    pub declaration: DeclarationIdentity,
    pub through: Option<QualifiedIdentity>,
}

/// The resources, declarations and runtime usages of a usage-complete scope index.
#[derive(Clone, Debug, Default)]
pub struct PlacementIndex {
    pub resources: Vec<ResourceRecord>,
    pub declarations: Vec<DeclarationRecord>,
    pub usages: Vec<PlacementUsage>,
}

/// The placement diagnostic codes.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PlacementCode {
    LocalNeededByDescendant,
    OverBroadInherited,
    RequiresGlobalPlacement,
    UnusedDeclaration,
    OverBroadGlobal,
}

impl PlacementCode {
    /// The placement code with Python's `ScopeDiagnosticCode` value `code`.
    pub fn parse(code: &str) -> Option<Self> {
        [
            Self::LocalNeededByDescendant,
            Self::OverBroadInherited,
            Self::RequiresGlobalPlacement,
            Self::UnusedDeclaration,
            Self::OverBroadGlobal,
        ]
        .into_iter()
        .find(|item| item.as_str() == code)
    }

    /// Python's `ScopeDiagnosticCode` value.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::LocalNeededByDescendant => "S007",
            Self::OverBroadInherited => "S008",
            Self::RequiresGlobalPlacement => "S009",
            Self::UnusedDeclaration => "S010",
            Self::OverBroadGlobal => "S024",
        }
    }
}

/// A misplaced or unused declaration, by its position in the index's declarations.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PlacementDiagnostic {
    pub declaration: usize,
    pub code: PlacementCode,
    pub message: String,
}

/// Where a declaration's consumers require it, and their sorted labels.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RequiredPlacement {
    pub scope: ScopeKind,
    pub path: Option<String>,
    pub consumers: Vec<String>,
}

/// A declaration's placement after a resource move, by its position in the index.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Relocation {
    pub declaration: usize,
    pub path: String,
    pub scope: ScopeKind,
    pub ownership_root: OwnershipRoot,
    pub owning_path: Option<String>,
    /// The destination role keeps its files in groups, but this file has none to keep.
    pub requires_group: bool,
}

/// The fields Python orders scope diagnostics by.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DiagnosticOrderKey {
    pub path: Option<String>,
    pub line: Option<i64>,
    pub column: Option<i64>,
    pub code: String,
    pub message: String,
}
