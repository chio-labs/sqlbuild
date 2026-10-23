//! Write the project's files at the base commit into a directory, without touching the checkout.

use std::path::{Path, PathBuf};

use crate::git_revisions::_helpers::failures::export_failed;
use crate::git_revisions::_helpers::git_command::git_output;
use crate::git_revisions::constants::INDEX_FILE_ENV;
use crate::git_revisions::errors::GitRevisionError;
use crate::git_revisions::models::GitBase;

fn tree_of(base: &GitBase) -> String {
    let prefix: &str = base.project_prefix.trim_end_matches('/');
    if prefix.is_empty() {
        format!("{}^{{tree}}", base.merge_base)
    } else {
        format!("{}:{prefix}", base.merge_base)
    }
}

/// Write the base project tree to `destination` through a private index; `false` without a project.
pub fn export_git_tree(base: &GitBase, destination: &Path) -> Result<bool, GitRevisionError> {
    let root: &Path = &base.repository_root;
    let tree: String = tree_of(base);
    if git_output(root, &["cat-file", "-e", &tree], &[]).is_err() {
        return Ok(false);
    }
    std::fs::create_dir_all(destination)
        .map_err(|error| export_failed(base, &error.to_string()))?;
    let index: PathBuf = destination.with_extension("index");
    let environment: [(&str, &Path); 1] = [(INDEX_FILE_ENV, index.as_path())];
    let mut prefix: String = destination.to_string_lossy().replace('\\', "/");
    if !prefix.ends_with('/') {
        prefix.push('/');
    }
    let exported: Result<(), GitRevisionError> =
        git_output(root, &["read-tree", &tree], &environment)
            .and_then(|_| {
                git_output(
                    root,
                    &[
                        "checkout-index",
                        "--all",
                        "--force",
                        &format!("--prefix={prefix}"),
                    ],
                    &environment,
                )
            })
            .map(|_| ())
            .map_err(|failure| export_failed(base, failure.detail()));
    let _ = std::fs::remove_file(&index);
    exported?;
    Ok(true)
}
