//! What one artifact write or publication did.

use std::path::PathBuf;

/// The files a write batch replaced and left unchanged.
#[derive(Debug, Default, PartialEq, Eq)]
pub struct WrittenArtifacts {
    pub written: usize,
    pub unchanged: usize,
}

/// How staged artifacts reached the compiled directory.
#[derive(Debug, PartialEq, Eq)]
pub enum Publication {
    /// The staged files differ from the expected set; nothing was published.
    StagedChanged,
    /// The whole staged directory became the compiled directory.
    MovedTree,
    /// Each staged file was published at its compiled path, in this order.
    Files(Vec<(PathBuf, PathBuf)>),
}
