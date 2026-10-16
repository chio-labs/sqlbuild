//! One discovered project path.

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
