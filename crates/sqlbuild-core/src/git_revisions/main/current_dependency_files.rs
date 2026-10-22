//! The git-tracked Python dependency manifests and lock files of a project in the checkout.

use std::path::Path;

use crate::git_revisions::_helpers::dependency_files::{
    directories, is_dependency_file, normalised,
};
use crate::git_revisions::_helpers::failures::export_failed;
use crate::git_revisions::_helpers::git_command::git_output;
use crate::git_revisions::errors::GitRevisionError;
use crate::git_revisions::models::GitBase;

/// `(repository path, text)` of each tracked dependency file as the checkout has it, sorted.
pub fn current_dependency_files(base: &GitBase) -> Result<Vec<(String, String)>, GitRevisionError> {
    let root: &Path = &base.repository_root;
    let mut files: Vec<(String, String)> = Vec::new();
    for directory in directories(base) {
        let listing: String = git_output(
            root,
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
        for path in listing.split('\0').filter(|path| !path.is_empty()) {
            let Some(name) = path.strip_prefix(directory.as_str()) else {
                continue;
            };
            if name.contains('/') || !is_dependency_file(name) {
                continue;
            }
            let text: String = match std::fs::read(root.join(path)) {
                Ok(bytes) => String::from_utf8_lossy(&bytes).into_owned(),
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => continue,
                Err(error) => return Err(export_failed(base, &error.to_string())),
            };
            files.push((path.to_owned(), normalised(&text)));
        }
    }
    files.sort();
    Ok(files)
}
