//! Declaration roles, named kinds and the scope labels placement messages print.

use crate::scope_index::models::{DeclarationKind, ScopeKind};

/// Kinds declared in named roles, which resolve by name rather than by SQL reference.
pub(crate) fn is_named_kind(kind: DeclarationKind) -> bool {
    !matches!(
        kind,
        DeclarationKind::Macro | DeclarationKind::Enum | DeclarationKind::Constant
    )
}

/// Python's `DECLARATION_ROLE_PARTS`.
pub(crate) fn role_parts(kind: DeclarationKind) -> &'static [&'static str] {
    match kind {
        DeclarationKind::Macro => &["macros"],
        DeclarationKind::Enum => &["enums"],
        DeclarationKind::Constant => &["constants"],
        DeclarationKind::Audit => &["audits", "generic"],
        DeclarationKind::SingularAudit => &["audits", "singular"],
        DeclarationKind::Schema => &["schemas"],
        DeclarationKind::SqlHook => &["hooks", "sql"],
        DeclarationKind::PythonHook => &["hooks", "python"],
    }
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
