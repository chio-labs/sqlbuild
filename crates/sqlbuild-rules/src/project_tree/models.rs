//! One discovered project path.

use std::ffi::OsString;
use std::path::PathBuf;

/// A project-relative file or directory the tree lists.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ProjectTreeEntry {
    pub relative: PathBuf,
    pub is_file: bool,
}

/// How the walk treats one directory entry.
pub(crate) enum EntryKind {
    Link,
    Directory,
    Other,
}

/// A pure path as `pathlib` splits it: its anchor (drive and root), then each component.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct PureParts {
    pub(crate) anchor: OsString,
    pub(crate) tail: Vec<OsString>,
}
