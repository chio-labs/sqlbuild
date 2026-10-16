//! How the project walk classifies, filters and names directory entries.

use std::ffi::{OsStr, OsString};
use std::fs::DirEntry;
use std::path::{Path, PathBuf};

use crate::project_tree::constants::{EXCLUDED_ROOTS, HIDDEN_PREFIX, POSIX_SEPARATOR};
use crate::project_tree::models::EntryKind;

/// How the walk treats one directory entry, without following links.
pub(crate) fn kind(entry: &DirEntry) -> EntryKind {
    match entry.file_type() {
        Ok(file_type) if file_type.is_symlink() => EntryKind::Link,
        Ok(file_type) if file_type.is_dir() => EntryKind::Directory,
        _ => EntryKind::Other,
    }
}

/// Whether the walk lists and enters a directory entry.
pub(crate) fn listed_directory(entry: &DirEntry, at_root: bool) -> bool {
    let name: OsString = entry.file_name();
    let name: &[u8] = name.as_encoded_bytes();
    if name.first() == Some(&HIDDEN_PREFIX) {
        return false;
    }
    !(at_root
        && EXCLUDED_ROOTS
            .iter()
            .any(|excluded| name == excluded.as_bytes()))
}

/// The project-relative `as_posix()` spelling of `name` inside `relative`.
pub(crate) fn posix_child(relative: &Path, name: &OsStr) -> PathBuf {
    if relative.as_os_str().is_empty() {
        return PathBuf::from(name);
    }
    let mut child: OsString = relative.as_os_str().to_os_string();
    child.push(POSIX_SEPARATOR);
    child.push(name);
    PathBuf::from(child)
}
