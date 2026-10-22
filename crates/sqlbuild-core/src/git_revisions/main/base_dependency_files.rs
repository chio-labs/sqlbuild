//! The Python dependency manifests and lock files of a project at the merge base.

use std::path::Path;

use crate::git_revisions::_helpers::dependency_files::{
    directories, is_dependency_file, normalised,
};
use crate::git_revisions::_helpers::failures::export_failed;
use crate::git_revisions::_helpers::git_command::{GitFailure, git_output};
use crate::git_revisions::errors::GitRevisionError;
use crate::git_revisions::models::GitBase;

/// `(repository path, text)` of each dependency file at the merge base, sorted.
pub fn base_dependency_files(base: &GitBase) -> Result<Vec<(String, String)>, GitRevisionError> {
    let root: &Path = &base.repository_root;
    let mut files: Vec<(String, String)> = Vec::new();
    for directory in directories(base) {
        let tree: String = format!("{}:{directory}", base.merge_base);
        let listing: String = match git_output(root, &["ls-tree", "--name-only", &tree], &[]) {
            Ok(listing) => listing,
            Err(GitFailure::Failed(_)) => continue,
            Err(failure) => return Err(export_failed(base, failure.detail())),
        };
        for name in listing.lines().filter(|name| is_dependency_file(name)) {
            let path: String = format!("{directory}{name}");
            let blob: String = format!("{}:{path}", base.merge_base);
            let text: String = git_output(root, &["show", &blob], &[])
                .map_err(|failure| export_failed(base, failure.detail()))?;
            files.push((path, normalised(&text)));
        }
    }
    files.sort();
    Ok(files)
}
