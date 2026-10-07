//! One directory listing with the entry type facts Python's `os.scandir` reports.

use crate::models::StageDeferral;
use crate::tree::models::TreeEntry;
use std::fs::DirEntry;
use std::path::Path;

/// List a directory; an unreadable directory lists as empty, as in Python's snapshot.
pub(crate) fn list_directory(directory: &Path) -> Result<Vec<TreeEntry>, StageDeferral> {
    let Ok(entries) = std::fs::read_dir(directory) else {
        return Ok(Vec::new());
    };
    let mut listing: Vec<TreeEntry> = Vec::new();
    for entry in entries {
        let Ok(entry) = entry else {
            return Ok(Vec::new());
        };
        listing.push(tree_entry(&entry)?);
    }
    Ok(listing)
}

fn tree_entry(entry: &DirEntry) -> Result<TreeEntry, StageDeferral> {
    let name = entry
        .file_name()
        .into_string()
        .map_err(|name| StageDeferral {
            reason: format!("file name is not UTF-8: {}", name.to_string_lossy()),
        })?;
    let (is_dir, is_walkable_dir) = match entry.file_type() {
        Ok(file_type) if file_type.is_symlink() => (link_target_is_dir(entry), false),
        Ok(file_type) => (file_type.is_dir(), file_type.is_dir()),
        Err(_unreadable) => (false, false),
    };
    Ok(TreeEntry {
        name,
        is_dir,
        is_walkable_dir,
    })
}

fn link_target_is_dir(entry: &DirEntry) -> bool {
    match std::fs::metadata(entry.path()) {
        Ok(metadata) => metadata.is_dir(),
        Err(_dangling) => false,
    }
}

/// Join a `/`-separated relative directory and an entry name.
pub(crate) fn join_relative(directory: &str, name: &str) -> String {
    if directory.is_empty() {
        name.to_owned()
    } else {
        format!("{directory}/{name}")
    }
}
