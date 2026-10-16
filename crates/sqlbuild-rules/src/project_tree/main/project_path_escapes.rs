//! Whether a project path leaves the project.

use std::path::Path;

use crate::project_tree::_helpers::relative_paths::escapes;

/// `Path(path).is_absolute() or ".." in Path(path).parts` with this platform's path rules.
#[must_use]
pub fn project_path_escapes(path: &Path) -> bool {
    escapes(path)
}
