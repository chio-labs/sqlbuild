//! The real file a project-relative path names, when rules may read it.

use std::path::{Path, PathBuf};

use crate::project_tree::_helpers::files::{
    inside, joined, points_to_file, real_path, regular_file, tracked,
};
use crate::project_tree::_helpers::relative_paths::{escapes, pure_parts};
use crate::project_tree::errors::ProjectTreeFileError;
use crate::project_tree::models::PureParts;

/// The tracked file inside the resolved `root` that the project-relative `path` names.
pub(crate) fn project_tree_file(root: &Path, path: &Path) -> Result<PathBuf, ProjectTreeFileError> {
    if escapes(path) {
        return Err(ProjectTreeFileError::Escapes);
    }
    if path.as_os_str().as_encoded_bytes().contains(&0) {
        return Err(ProjectTreeFileError::EmbeddedNul);
    }
    let parts: PureParts = pure_parts(path);
    if let Some(regular) = regular_file(root, &parts) {
        return tracked(regular);
    }
    let lexical: PathBuf = joined(root, &parts);
    let candidate: PathBuf = real_path(&lexical).unwrap_or(lexical);
    if !inside(&candidate, root) || !points_to_file(&candidate)? {
        return Err(ProjectTreeFileError::Missing);
    }
    let candidate: PathBuf = tracked(candidate)?;
    if candidate.is_symlink() {
        return Err(ProjectTreeFileError::Symlink);
    }
    Ok(candidate)
}
