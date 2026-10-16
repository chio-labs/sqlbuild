use std::path::{Path, PathBuf};

use crate::project_tree::_helpers::files::real_path;

/// `path.resolve()` of an existing path without Windows' verbatim prefix, or `path` when it cannot be resolved.
pub fn project_real_path(path: &Path) -> PathBuf {
    real_path(path).unwrap_or_else(|_| path.to_path_buf())
}
