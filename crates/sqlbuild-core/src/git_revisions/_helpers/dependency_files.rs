//! Which files record a project's Python dependencies, and where they are looked for.

use std::collections::BTreeSet;
use std::path::Path;

use crate::git_revisions::_helpers::failures::export_failed;
use crate::git_revisions::_helpers::git_command::git_output;
use crate::git_revisions::constants::{DEPENDENCY_FILE_NAMES, REQUIREMENTS_FILE_AFFIXES};
use crate::git_revisions::errors::GitRevisionError;
use crate::git_revisions::models::GitBase;

/// Whether `name` is a Python dependency manifest or lock file.
pub(crate) fn is_dependency_file(name: &str) -> bool {
    let (prefix, suffix) = REQUIREMENTS_FILE_AFFIXES;
    DEPENDENCY_FILE_NAMES.contains(&name) || (name.starts_with(prefix) && name.ends_with(suffix))
}

/// The repository root and the project directory, as repository-relative directory prefixes.
pub(crate) fn directories(base: &GitBase) -> BTreeSet<String> {
    let project: &str = base.project_prefix.trim_end_matches('/');
    let mut directories: BTreeSet<String> = BTreeSet::from([String::new()]);
    if !project.is_empty() {
        directories.insert(format!("{project}/"));
    }
    directories
}

/// `text` with CRLF line endings as LF and surrounding whitespace removed, as git stores it.
pub(crate) fn normalised(text: &str) -> String {
    text.replace("\r\n", "\n").trim().to_owned()
}

/// Repository paths of the dependency files git tracks directly in `directory`.
pub(crate) fn tracked_dependency_paths(
    base: &GitBase,
    directory: &str,
) -> Result<Vec<String>, GitRevisionError> {
    let listing: String = git_output(
        &base.repository_root,
        &[
            "ls-files",
            "-z",
            "--full-name",
            "--",
            &format!("{directory}*"),
        ],
        &[],
    )
    .map_err(|failure| export_failed(base, failure.detail()))?;
    Ok(listing
        .split('\0')
        .filter_map(|path| {
            let name: &str = path.strip_prefix(directory)?;
            (!name.contains('/') && is_dependency_file(name)).then(|| path.to_owned())
        })
        .collect())
}

/// The normalised checkout text of repository path `path`, or `None` when it was deleted.
pub(crate) fn checkout_text(
    base: &GitBase,
    path: &str,
) -> Result<Option<String>, GitRevisionError> {
    let file: &Path = &base.repository_root.join(path);
    match std::fs::read(file) {
        Ok(bytes) => Ok(Some(normalised(&String::from_utf8_lossy(&bytes)))),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(export_failed(base, &error.to_string())),
    }
}
