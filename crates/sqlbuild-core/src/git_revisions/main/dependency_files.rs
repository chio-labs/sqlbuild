//! The Python dependency manifests and lock files of a project, at the base and in the checkout.

use std::collections::BTreeSet;
use std::path::Path;

use crate::git_revisions::_helpers::failures::export_failed;
use crate::git_revisions::_helpers::git_command::{GitFailure, git_output};
use crate::git_revisions::constants::{DEPENDENCY_FILE_NAMES, REQUIREMENTS_FILE_AFFIXES};
use crate::git_revisions::errors::GitRevisionError;
use crate::git_revisions::models::GitBase;

fn is_dependency_file(name: &str) -> bool {
    let (prefix, suffix) = REQUIREMENTS_FILE_AFFIXES;
    DEPENDENCY_FILE_NAMES.contains(&name) || (name.starts_with(prefix) && name.ends_with(suffix))
}

/// The repository root and the project directory, as repository-relative directory prefixes.
fn directories(base: &GitBase) -> BTreeSet<String> {
    let project: &str = base.project_prefix.trim_end_matches('/');
    let mut directories: BTreeSet<String> = BTreeSet::from([String::new()]);
    if !project.is_empty() {
        directories.insert(format!("{project}/"));
    }
    directories
}

/// `(repository path, trimmed text)` of each dependency file at the merge base, sorted.
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
            files.push((path, text));
        }
    }
    files.sort();
    Ok(files)
}

/// `(repository path, trimmed text)` of each dependency file in the checkout, sorted.
pub fn current_dependency_files(base: &GitBase) -> std::io::Result<Vec<(String, String)>> {
    let mut files: Vec<(String, String)> = Vec::new();
    for directory in directories(base) {
        let entries: std::fs::ReadDir =
            match std::fs::read_dir(base.repository_root.join(&directory)) {
                Ok(entries) => entries,
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => continue,
                Err(error) => return Err(error),
            };
        for entry in entries {
            let entry: std::fs::DirEntry = entry?;
            let name: String = entry.file_name().to_string_lossy().into_owned();
            if entry.path().is_file() && is_dependency_file(&name) {
                let text: String = std::fs::read_to_string(entry.path())?;
                files.push((format!("{directory}{name}"), text.trim().to_owned()));
            }
        }
    }
    files.sort();
    Ok(files)
}
