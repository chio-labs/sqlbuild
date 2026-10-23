//! The merge base of a ref and `HEAD` for the repository containing a project.

use std::path::{Path, PathBuf};

use crate::git_revisions::_helpers::git_command::{GitFailure, git_output};
use crate::git_revisions::constants::{
    DEPTH_HELP, NO_MERGE_BASE_CODE, NOT_A_REPOSITORY_CODE, SHALLOW_TRUE, UNKNOWN_REF_CODE,
};
use crate::git_revisions::errors::GitRevisionError;
use crate::git_revisions::models::GitBase;

fn not_a_repository(project_dir: &Path, failure: &GitFailure) -> GitRevisionError {
    let message: String = match failure {
        GitFailure::Unavailable(detail) => {
            format!("--since needs git, which could not be run: {detail}")
        }
        GitFailure::Failed(_) => format!(
            "--since needs a git repository, but {} is not inside one",
            project_dir.display()
        ),
    };
    GitRevisionError {
        message,
        code: NOT_A_REPOSITORY_CODE,
        help: "Run the command inside a git checkout of the project, or drop --since".to_owned(),
    }
}

fn is_shallow(root: &Path) -> bool {
    git_output(root, &["rev-parse", "--is-shallow-repository"], &[])
        .is_ok_and(|value| value == SHALLOW_TRUE)
}

/// Resolve `reference` and `HEAD` in the repository of `project_dir` to their merge base.
pub fn resolve_git_base(project_dir: &Path, reference: &str) -> Result<GitBase, GitRevisionError> {
    let root: PathBuf = git_output(project_dir, &["rev-parse", "--show-toplevel"], &[])
        .map(PathBuf::from)
        .map_err(|failure| not_a_repository(project_dir, &failure))?;
    let prefix: String = git_output(project_dir, &["rev-parse", "--show-prefix"], &[])
        .map_err(|failure| not_a_repository(project_dir, &failure))?;
    let shallow: bool = is_shallow(&root);
    let commit: String = git_output(
        &root,
        &[
            "rev-parse",
            "--verify",
            "--quiet",
            "--end-of-options",
            &format!("{reference}^{{commit}}"),
        ],
        &[],
    )
    .map_err(|_| GitRevisionError {
        message: format!("Git ref '{reference}' does not name a commit in this repository"),
        code: UNKNOWN_REF_CODE,
        help: if shallow {
            format!(
                "This is a shallow clone; fetch the ref first, for example `git fetch origin \
                 <branch>`, with enough depth to reach the merge base. {DEPTH_HELP}"
            )
        } else {
            "Check the spelling, or fetch the ref first, for example `git fetch origin <branch>`"
                .to_owned()
        },
    })?;
    let merge_base: String =
        git_output(&root, &["merge-base", &commit, "HEAD"], &[]).map_err(|failure| {
            if shallow {
                GitRevisionError {
                    message: format!(
                        "Cannot find the merge base of '{reference}' and HEAD: this is a shallow \
                         clone without the shared history"
                    ),
                    code: NO_MERGE_BASE_CODE,
                    help: DEPTH_HELP.to_owned(),
                }
            } else {
                let detail: &str = failure.detail();
                GitRevisionError {
                    message: if detail.is_empty() {
                        format!("'{reference}' and HEAD share no history")
                    } else {
                        format!("Cannot find the merge base of '{reference}' and HEAD: {detail}")
                    },
                    code: NO_MERGE_BASE_CODE,
                    help: "Pass a ref that shares history with HEAD, such as the branch this \
                           work started from"
                        .to_owned(),
                }
            }
        })?;
    Ok(GitBase {
        reference: reference.to_owned(),
        merge_base,
        repository_root: root,
        project_prefix: prefix,
    })
}
