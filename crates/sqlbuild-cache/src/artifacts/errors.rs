//! Why compiled artifacts could not be written or published.

use std::path::PathBuf;

/// An artifact write failed at `path`.
#[derive(Debug)]
pub enum ArtifactError {
    /// The operating system refused an operation on `path`.
    Io {
        path: PathBuf,
        error: std::io::Error,
    },
    /// The operating system refused to move `source` to `path`.
    Move {
        source: PathBuf,
        path: PathBuf,
        error: std::io::Error,
    },
    /// The file already at `path` is not UTF-8, which Python reports as a decode error.
    ExistingNotUtf8 { path: PathBuf },
}
