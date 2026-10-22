//! The Python dependency manifests and lock files of a project in the checkout.

use crate::git_revisions::_helpers::dependency_files::{directories, is_dependency_file};
use crate::git_revisions::models::GitBase;

/// `(repository path, trimmed text)` of each dependency file in the checkout, sorted.
pub fn current_dependency_files(base: &GitBase) -> std::io::Result<Vec<(String, String)>> {
    let mut files: Vec<(String, String)> = Vec::new();
    for directory in directories(base) {
        let entries: std::fs::ReadDir =
            match std::fs::read_dir(base.repository_root.join(&directory)) {
                Ok(entries) => entries,
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => continue,
                Err(error) => return Err(error),
            };
        for entry in entries {
            let entry: std::fs::DirEntry = entry?;
            let name: String = entry.file_name().to_string_lossy().into_owned();
            if entry.path().is_file() && is_dependency_file(&name) {
                let text: String = std::fs::read_to_string(entry.path())?;
                files.push((format!("{directory}{name}"), text.trim().to_owned()));
            }
        }
    }
    files.sort();
    Ok(files)
}
