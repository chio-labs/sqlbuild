//! The error of a base revision that cannot be read.

use crate::git_revisions::constants::EXPORT_FAILED_CODE;
use crate::git_revisions::errors::GitRevisionError;
use crate::git_revisions::models::GitBase;

/// The project at the merge base cannot be read, with git's `detail`.
pub(crate) fn export_failed(base: &GitBase, detail: &str) -> GitRevisionError {
    GitRevisionError {
        message: format!(
            "Cannot read the project at merge base {}: {detail}",
            base.merge_base
        ),
        code: EXPORT_FAILED_CODE,
        help: "Check that the repository is readable and complete, for example with `git fsck`"
            .to_owned(),
    }
}
