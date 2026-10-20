//! The message of a declaration whose scope path or owning path is rejected.

use crate::scope_index::constants::CURRENT_PATH_COMPONENT;
use crate::scope_index::main::normalize_scope_path::normalize_scope_path;
use crate::scope_index::models::{DeclaredScope, ScopePathFailure};

/// The `InvalidScopePathError` message of the first path Python's visibility check rejects.
#[must_use]
pub fn declared_scope_path_message(declared: &DeclaredScope, label: &str) -> String {
    let owner: &str = declared
        .owning_path
        .as_deref()
        .filter(|path| !path.is_empty())
        .unwrap_or(CURRENT_PATH_COMPONENT);
    let (path, failure) = match normalize_scope_path(label) {
        Err(failure) => (label, failure),
        Ok(_) => match normalize_scope_path(owner) {
            Err(failure) => (owner, failure),
            Ok(_) => (label, ScopePathFailure::NotProjectRelative),
        },
    };
    match failure {
        ScopePathFailure::NotProjectRelative => {
            format!("Scope path must be project-relative: {path}")
        }
        ScopePathFailure::EscapesProject => format!("Scope path escapes the project: {path}"),
    }
}
