//! One directory listing with the entry type facts Python's `os.scandir` reports.

use crate::tree::_helpers::raw_names::raw_segment;
use crate::tree::models::TreeEntry;
use std::fs::{DirEntry, FileType};
use std::path::Path;

/// List a directory; an unreadable directory lists as empty, as in Python's snapshot.
pub(crate) fn list_directory(directory: &Path) -> Vec<TreeEntry> {
    let Ok(entries) = std::fs::read_dir(directory) else {
        return Vec::new();
    };
    let mut listing: Vec<TreeEntry> = Vec::new();
    for entry in entries {
        let Ok(entry) = entry else {
            return Vec::new();
        };
        listing.push(tree_entry(&entry));
    }
    listing
}

fn tree_entry(entry: &DirEntry) -> TreeEntry {
    let (name, segment, raw_name) = match entry.file_name().into_string() {
        Ok(name) => (name.clone(), name, None),
        Err(raw) => {
            let lossy: String = raw.to_string_lossy().into_owned();
            let segment: String = raw_segment(&lossy, &raw);
            (lossy, segment, Some(raw))
        }
    };
    let (is_dir, is_walkable_dir) = match entry.file_type() {
        Ok(file_type) if is_junction(entry, &file_type) => (true, true),
        Ok(file_type) if file_type.is_symlink() => (link_target_is_dir(entry), false),
        Ok(file_type) => (file_type.is_dir(), file_type.is_dir()),
        Err(_unreadable) => (false, false),
    };
    TreeEntry {
        name,
        raw_name,
        segment,
        is_dir,
        is_walkable_dir,
    }
}

/// An NTFS junction, which Python's `os.scandir` reports as a real directory and walks into.
#[cfg(windows)]
fn is_junction(entry: &DirEntry, file_type: &FileType) -> bool {
    file_type.is_symlink() && matches!(junction::exists(entry.path()), Ok(true))
}

#[cfg(not(windows))]
fn is_junction(_entry: &DirEntry, _file_type: &FileType) -> bool {
    false
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
