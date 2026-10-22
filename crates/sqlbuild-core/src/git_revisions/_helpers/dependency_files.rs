//! Which files record a project's Python dependencies, and where they are looked for.

use std::collections::BTreeSet;

use crate::git_revisions::constants::{DEPENDENCY_FILE_NAMES, REQUIREMENTS_FILE_AFFIXES};
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
