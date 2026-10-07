//! The declaration layout facts native discovery hands to the Python discovery helpers.

use crate::models::DiscoveryFailure;

/// The kinds a macro, enum or constant declaration root holds (Python's `DeclarationKind`).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DeclarationKind {
    Macro,
    Enum,
    Constant,
}

impl DeclarationKind {
    /// Python's enum value.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Macro => "macro",
            Self::Enum => "enum",
            Self::Constant => "constant",
        }
    }
}

/// Python's `ScopeKind` for a declaration root.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ScopeKind {
    Global,
    Inherited,
    Local,
}

impl ScopeKind {
    /// Python's enum value.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Global => "global",
            Self::Inherited => "inherited",
            Self::Local => "local",
        }
    }
}

/// Python's `_DeclarationFileFacts` with `/`-separated project-relative paths.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DeclarationFileFact {
    pub relative_path: String,
    pub kind: DeclarationKind,
    pub scope_kind: ScopeKind,
    pub ownership_root: String,
    pub owning_path: Option<String>,
    pub declaration_root: String,
}

/// A `_sqlbuild/` declaration group below a concrete owner, with its canonical root.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DeclarationGroup {
    pub root: String,
    pub directory: String,
}

/// The validated declaration layout, or the first failure Python's own scan raises.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DeclarationLayout {
    /// Every macro, enum and constant file, by relative path.
    pub file_facts: Result<Vec<DeclarationFileFact>, DiscoveryFailure>,
    /// The declaration groups the named roles use, once the named layout is valid.
    pub named_groups: Result<Vec<DeclarationGroup>, DiscoveryFailure>,
}
