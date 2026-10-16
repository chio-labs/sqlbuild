//! Resolution of one project-relative path to a real, readable project file.

use std::ffi::OsStr;
use std::os::unix::ffi::OsStrExt;
use std::path::{Path, PathBuf};

use sqlbuild_core::posix_path::main::posix_suffix::posix_suffix;

use crate::project_tree::constants::{MISSING_FILE_ERRNOS, TRACKED_TEXT_SUFFIXES};
use crate::project_tree::errors::ProjectTreeFileError;

/// `root` joined with the raw path components.
pub(crate) fn joined(root: &Path, parts: &[&[u8]]) -> PathBuf {
    let mut path: PathBuf = root.to_path_buf();
    path.extend(parts.iter().map(|part| OsStr::from_bytes(part)));
    path
}

/// `Path.is_file()`: false for the failures `pathlib` ignores, the failure otherwise.
pub(crate) fn points_to_file(path: &Path) -> Result<bool, ProjectTreeFileError> {
    match std::fs::metadata(path) {
        Ok(metadata) => Ok(metadata.is_file()),
        Err(error) => match error.raw_os_error() {
            Some(errno) if !MISSING_FILE_ERRNOS.contains(&errno) => {
                Err(ProjectTreeFileError::Unreadable {
                    path: path.to_path_buf(),
                    errno,
                })
            }
            _ => Ok(false),
        },
    }
}

/// A regular, non-link file under the project's resolved parent directory of the path.
pub(crate) fn regular_file(root: &Path, parts: &[&[u8]]) -> Option<PathBuf> {
    let (name, parent) = parts.split_last()?;
    let directory: PathBuf = match std::fs::canonicalize(joined(root, parent)) {
        Ok(directory) => directory,
        Err(_unresolved) => return None,
    };
    if !directory.starts_with(root) {
        return None;
    }
    let candidate: PathBuf = directory.join(OsStr::from_bytes(name));
    match std::fs::symlink_metadata(&candidate) {
        Ok(metadata) => metadata.file_type().is_file().then_some(candidate),
        Err(_unreadable) => None,
    }
}

/// `candidate` when its lowercased suffix is a tracked text type.
pub(crate) fn tracked(candidate: PathBuf) -> Result<PathBuf, ProjectTreeFileError> {
    let name: String = candidate
        .file_name()
        .map(|name| name.to_string_lossy().into_owned())
        .unwrap_or_default();
    let suffix: String = posix_suffix(&name).to_lowercase();
    if TRACKED_TEXT_SUFFIXES.contains(&suffix.as_str()) {
        Ok(candidate)
    } else {
        Err(ProjectTreeFileError::Untracked)
    }
}
