//! Declaration roles, named kinds and the scope labels placement messages print.

use crate::scope_index::models::{DeclarationKind, ScopeKind};

/// Kinds declared in named roles, which resolve by name rather than by SQL reference.
pub(crate) fn is_named_kind(kind: DeclarationKind) -> bool {
    !matches!(
        kind,
        DeclarationKind::Macro | DeclarationKind::Enum | DeclarationKind::Constant
    )
}

/// How placement messages name a scope.
pub(crate) fn scope_label(scope: ScopeKind) -> &'static str {
    match scope {
        ScopeKind::Global => "project",
        ScopeKind::Inherited => "descendant-public",
        ScopeKind::Local => "exact-owner-private",
        ScopeKind::Private => "model-private",
    }
}
