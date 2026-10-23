//! The commit `HEAD` names in the repository containing a directory.

use std::path::Path;

use crate::git_revisions::_helpers::git_command::{GitFailure, git_output};

/// The full hash of `HEAD`, or `None` when `directory` is not in a git checkout with a commit.
#[must_use]
pub fn head_commit(directory: &Path) -> Option<String> {
    let found = git_output(
        directory,
        &["rev-parse", "--verify", "--quiet", "HEAD"],
        &[],
    );
    match found {
        Ok(commit) if !commit.is_empty() => Some(commit),
        Ok(_) | Err(GitFailure::Failed(_) | GitFailure::Unavailable(_)) => None,
    }
}
