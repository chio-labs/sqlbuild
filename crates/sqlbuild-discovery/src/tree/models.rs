//! One shared directory snapshot for a native discovery pass.

use crate::tree::_helpers::listing::join_relative;
use crate::tree::_helpers::raw_names::has_raw_segment;
use std::collections::HashMap;
use std::ffi::OsString;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, RwLock};

/// One directory entry, with the same type facts as Python's `DirectorySnapshotEntry`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct TreeEntry {
    /// The name, with bytes that are not valid UTF-8 replaced by `\u{FFFD}`.
    pub name: String,
    /// The real name when it is not valid UTF-8.
    pub raw_name: Option<OsString>,
    /// The name in relative paths: `name`, or a unique segment for a raw name.
    pub segment: String,
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
    /// The real names of listed entries that are not valid UTF-8, by relative path.
    pub(crate) raw_names: RwLock<HashMap<String, OsString>>,
}

impl ProjectTree {
    /// An empty snapshot of `directory`; listings are read on first use.
    pub fn new(directory: &Path) -> Self {
        Self {
            directory: directory.to_path_buf(),
            listings: Mutex::new(HashMap::new()),
            raw_names: RwLock::new(HashMap::new()),
        }
    }

    /// The absolute path of a `/`-separated project-relative path, using real listed names.
    pub fn absolute(&self, relative_path: &str) -> PathBuf {
        match self.raw_relative(relative_path) {
            Some(raw) => self.directory.join(raw),
            None => relative_path
                .split('/')
                .filter(|part| !part.is_empty())
                .fold(self.directory.clone(), |path, part| path.join(part)),
        }
    }

    /// The real relative path when a listed component of `relative_path` is not valid UTF-8.
    pub fn raw_relative(&self, relative_path: &str) -> Option<PathBuf> {
        if !has_raw_segment(relative_path) {
            return None;
        }
        let Ok(raw_names) = self.raw_names.read() else {
            return None;
        };
        let mut prefix = String::new();
        let mut raw = PathBuf::new();
        let mut undecodable = false;
        for part in relative_path.split('/').filter(|part| !part.is_empty()) {
            prefix = join_relative(&prefix, part);
            match raw_names.get(&prefix) {
                Some(name) => {
                    undecodable = true;
                    raw.push(name);
                }
                None => raw.push(part),
            }
        }
        undecodable.then_some(raw)
    }

    /// Whether a listed component of `relative_path` is not valid UTF-8.
    pub fn is_undecodable(&self, relative_path: &str) -> bool {
        has_raw_segment(relative_path)
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
