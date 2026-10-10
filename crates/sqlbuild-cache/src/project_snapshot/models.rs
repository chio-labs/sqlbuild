//! Stat identities of project paths, as Python's compile reuse records them.

/// One path's stat identity: kind code, size, mtime and ctime in nanoseconds, inode and link.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PathStamp {
    pub relative_path: String,
    pub kind: &'static str,
    pub size: u64,
    pub mtime_ns: i64,
    pub ctime_ns: i64,
    pub inode: u64,
    pub link: Option<String>,
}

/// What the walk skips or records by presence only.
#[derive(Clone, Debug, Default)]
pub struct SnapshotRules {
    /// Directory names skipped anywhere.
    pub excluded: Vec<String>,
    /// Directory names skipped only at the project root.
    pub excluded_root: Vec<String>,
    /// File name suffixes recorded by presence only.
    pub presence_suffixes: Vec<String>,
    /// Device and inode of files holding this command's output.
    pub output_files: Vec<(u64, u64)>,
}
