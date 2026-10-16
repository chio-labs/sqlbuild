//! How the project walk classifies and filters directory entries.

use std::fs::DirEntry;
use std::os::unix::ffi::OsStrExt;

use crate::project_tree::constants::{EXCLUDED_ROOTS, HIDDEN_PREFIX};
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
    let name = entry.file_name();
    if name.as_bytes().first() == Some(&HIDDEN_PREFIX) {
        return false;
    }
    !(at_root
        && EXCLUDED_ROOTS
            .iter()
            .any(|excluded| name.as_bytes() == excluded.as_bytes()))
}
