//! Whether a project path names a text file type rules may read.

use std::path::Path;

use sqlbuild_core::posix_path::main::posix_suffix::posix_suffix;

use crate::project_tree::constants::TRACKED_TEXT_SUFFIXES;

/// Whether the lowercased suffix of the path's name is a tracked text type.
#[must_use]
pub fn tracked_text_path(path: &Path) -> bool {
    let name: String = path
        .file_name()
        .map(|name| name.to_string_lossy().into_owned())
        .unwrap_or_default();
    TRACKED_TEXT_SUFFIXES.contains(&posix_suffix(&name).to_lowercase().as_str())
}
