//! One startup input and its file stamp.

use std::path::PathBuf;

/// The interpreter locations the stamps cover.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct StartupLocations {
    /// Import-path and site-packages directories, made absolute.
    pub directories: Vec<PathBuf>,
    /// Interpreter files, as given.
    pub files: Vec<PathBuf>,
    /// Interpreter prefixes whose `pyvenv.cfg` is stamped.
    pub prefixes: Vec<PathBuf>,
}

/// A path with its modification time in nanoseconds and size, both absent when it is missing.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct StartupStamp {
    pub path: PathBuf,
    pub modified_ns: Option<i64>,
    pub size: Option<u64>,
}
