use crate::placement::models::PlacementIndex;
use crate::scope_index::models::{DeclarationKind, ScopeKind};

/// A usage-complete index and the `(declaration, code, message)` diagnostics it raises.
pub(super) struct PlacementDiagnosticsTestCase {
    pub(super) description: &'static str,
    pub(super) index: fn() -> PlacementIndex,
    pub(super) expected_diagnostics: &'static [(usize, &'static str, &'static str)],
}

/// A placement and the folder a declaration with it lives in.
pub(super) struct DeclarationDirectoryTestCase {
    pub(super) description: &'static str,
    pub(super) kind: DeclarationKind,
    pub(super) scope: ScopeKind,
    pub(super) path: Option<&'static str>,
    pub(super) expected_directory: &'static str,
}

/// `(declaration, new path, owning path)` of one relocated declaration.
pub(super) type RelocationCase = (usize, &'static str, Option<&'static str>);

/// A resource move and each declaration it relocates.
pub(super) struct RelocationTestCase {
    pub(super) description: &'static str,
    pub(super) index: fn() -> PlacementIndex,
    pub(super) destination: &'static str,
    pub(super) expected_relocations: Option<&'static [RelocationCase]>,
}
