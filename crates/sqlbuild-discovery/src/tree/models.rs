//! One shared directory snapshot for a native discovery pass.

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

/// One directory entry, with the same type facts as Python's `DirectorySnapshotEntry`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct TreeEntry {
    pub name: String,
    /// `entry.is_dir()`, following symbolic links.
    pub is_dir: bool,
    /// `entry.is_dir(follow_symlinks=False)`: a real directory the walk descends into.
    pub is_walkable_dir: bool,
}

/// Directory listings read once per pass and shared by every query, keyed by relative path.
#[derive(Debug)]
pub struct ProjectTree {
    pub(crate) directory: PathBuf,
    pub(crate) listings: Mutex<HashMap<String, Arc<Vec<TreeEntry>>>>,
}

impl ProjectTree {
    /// An empty snapshot of `directory`; listings are read on first use.
    pub fn new(directory: &Path) -> Self {
        Self {
            directory: directory.to_path_buf(),
            listings: Mutex::new(HashMap::new()),
        }
    }

    /// The absolute path of a `/`-separated project-relative path.
    pub fn absolute(&self, relative_path: &str) -> PathBuf {
        relative_path
            .split('/')
            .filter(|part| !part.is_empty())
            .fold(self.directory.clone(), |path, part| path.join(part))
    }

    /// Python's `Path.is_dir()`: follows symbolic links and reports any failure as `false`.
    pub fn is_dir(&self, relative_path: &str) -> bool {
        match std::fs::metadata(self.absolute(relative_path)) {
            Ok(metadata) => metadata.is_dir(),
            Err(_unreadable) => false,
        }
    }

    /// Python's `Path.exists()`: follows symbolic links and reports any failure as `false`.
    pub fn exists(&self, relative_path: &str) -> bool {
        match std::fs::metadata(self.absolute(relative_path)) {
            Ok(_metadata) => true,
            Err(_missing) => false,
        }
    }
}
