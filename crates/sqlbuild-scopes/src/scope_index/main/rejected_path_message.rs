//! The message of a rejected scope path.

use crate::scope_index::models::{RejectedPath, ScopePathFailure};

/// Python's `InvalidScopePathError` message for a rejected path.
#[must_use]
pub fn rejected_path_message(rejected: &RejectedPath) -> String {
    match rejected.failure {
        ScopePathFailure::NotProjectRelative => {
            format!("Scope path must be project-relative: {}", rejected.path)
        }
        ScopePathFailure::EscapesProject => {
            format!("Scope path escapes the project: {}", rejected.path)
        }
    }
}
