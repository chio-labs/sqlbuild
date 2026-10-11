//! Python's `format_identity` of a resource or declaration.

use crate::scope_index::_helpers::identities::{declaration_text, resource_text};
use crate::scope_index::models::QualifiedIdentity;

/// `kind:name`, or `kind:owner_kind:owner_name.name` for a private declaration.
#[must_use]
pub fn format_identity(identity: &QualifiedIdentity) -> String {
    match identity {
        QualifiedIdentity::Resource(resource) => resource_text(resource),
        QualifiedIdentity::Declaration(declaration) => declaration_text(declaration),
    }
}
