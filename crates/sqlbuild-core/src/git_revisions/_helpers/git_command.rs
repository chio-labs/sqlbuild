//! Run one git command in a directory and read its trimmed standard output.

use std::path::Path;
use std::process::{Command, Output, Stdio};

use crate::git_revisions::constants::GIT_PROGRAM;

/// How one git command failed.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum GitFailure {
    /// git could not be started at all.
    Unavailable(String),
    /// git ran and exited unsuccessfully, with its trimmed standard error.
    Failed(String),
}

impl GitFailure {
    /// The failure text a message can quote.
    pub(crate) fn detail(&self) -> &str {
        match self {
            Self::Unavailable(detail) | Self::Failed(detail) => detail,
        }
    }
}

/// The trimmed stdout of `git <arguments>` run in `directory` with `environment` added.
pub(crate) fn git_output(
    directory: &Path,
    arguments: &[&str],
    environment: &[(&str, &Path)],
) -> Result<String, GitFailure> {
    let mut command: Command = Command::new(GIT_PROGRAM);
    command
        .current_dir(directory)
        .args(arguments)
        .stdin(Stdio::null())
        .env("GIT_TERMINAL_PROMPT", "0");
    for (name, value) in environment {
        command.env(name, value);
    }
    let output: Output = command
        .output()
        .map_err(|error| GitFailure::Unavailable(error.to_string()))?;
    if !output.status.success() {
        return Err(GitFailure::Failed(
            String::from_utf8_lossy(&output.stderr).trim().to_owned(),
        ));
    }
    Ok(String::from_utf8_lossy(&output.stdout).trim().to_owned())
}
