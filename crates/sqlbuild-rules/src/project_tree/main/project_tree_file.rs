//! The real file a project-relative path names, when rules may read it.

use std::os::unix::ffi::OsStrExt;
use std::path::{Path, PathBuf};

use crate::project_tree::_helpers::files::{joined, points_to_file, regular_file, tracked};
use crate::project_tree::_helpers::relative_paths::{escapes, parts};
use crate::project_tree::errors::ProjectTreeFileError;

/// The tracked file inside the resolved `root` that the project-relative `path` names.
pub fn project_tree_file(root: &Path, path: &Path) -> Result<PathBuf, ProjectTreeFileError> {
    if escapes(path) {
        return Err(ProjectTreeFileError::Escapes);
    }
    if path.as_os_str().as_bytes().contains(&0) {
        return Err(ProjectTreeFileError::EmbeddedNul);
    }
    let parts: Vec<&[u8]> = parts(path);
    if let Some(regular) = regular_file(root, &parts) {
        return tracked(regular);
    }
    let lexical: PathBuf = joined(root, &parts);
    let candidate: PathBuf = std::fs::canonicalize(&lexical).unwrap_or(lexical);
    if !candidate.starts_with(root) || !points_to_file(&candidate)? {
        return Err(ProjectTreeFileError::Missing);
    }
    let candidate: PathBuf = tracked(candidate)?;
    if candidate.is_symlink() {
        return Err(ProjectTreeFileError::Symlink);
    }
    Ok(candidate)
}
