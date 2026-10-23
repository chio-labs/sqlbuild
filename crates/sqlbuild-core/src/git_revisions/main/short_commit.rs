//! The abbreviated commit hash shown in progress and summaries.

use crate::git_revisions::constants::SHORT_COMMIT_LENGTH;

/// The first hex digits of `commit`.
pub fn short_commit(commit: &str) -> &str {
    commit.get(..SHORT_COMMIT_LENGTH).unwrap_or(commit)
}
