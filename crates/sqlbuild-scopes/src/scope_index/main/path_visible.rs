//! Python's `declaration_visibility(...) is not None` for an authored consumer path.

use crate::scope_index::_helpers::visibility::authored_path_visibility;
use crate::scope_index::models::{DeclaredScope, ScopeDeferral};

/// Whether a declaration with these scope facts is visible from the authored `path`.
pub fn path_visible(declared: &DeclaredScope, path: &str) -> Result<bool, ScopeDeferral> {
    authored_path_visibility(declared, path)
}
