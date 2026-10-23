//! The commit `HEAD` names in the repository containing a directory.

use std::path::Path;

use crate::git_revisions::_helpers::git_command::git_output;

/// The full hash of `HEAD`, or `None` when `directory` is not in a git checkout with a commit.
#[must_use]
pub fn head_commit(directory: &Path) -> Option<String> {
    git_output(
        directory,
        &["rev-parse", "--verify", "--quiet", "HEAD"],
        &[],
    )
    .ok()
    .filter(|commit| !commit.is_empty())
}
