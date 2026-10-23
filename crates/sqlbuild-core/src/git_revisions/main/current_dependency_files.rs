//! The git-tracked Python dependency manifests and lock files of a project in the checkout.

use crate::git_revisions::_helpers::dependency_files::{
    checkout_text, directories, tracked_dependency_paths,
};
use crate::git_revisions::errors::GitRevisionError;
use crate::git_revisions::models::GitBase;

/// `(repository path, text)` of each tracked dependency file as the checkout has it, sorted.
pub fn current_dependency_files(base: &GitBase) -> Result<Vec<(String, String)>, GitRevisionError> {
    let mut files: Vec<(String, String)> = Vec::new();
    for directory in directories(base) {
        for path in tracked_dependency_paths(base, &directory)? {
            if let Some(text) = checkout_text(base, &path)? {
                files.push((path, text));
            }
        }
    }
    files.sort();
    Ok(files)
}
