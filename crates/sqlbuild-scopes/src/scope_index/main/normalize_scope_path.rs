//! Python's scope `normalize_path`.

use crate::scope_index::_helpers::paths::normalized_path;
use crate::scope_index::models::ScopePathFailure;

/// The normalized project-relative path, or why Python rejects `path`.
pub fn normalize_scope_path(path: &str) -> Result<String, ScopePathFailure> {
    normalized_path(path)
}
