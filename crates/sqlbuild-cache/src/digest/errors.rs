//! Why a project fingerprint could not cover every file.

use std::fmt;

/// A file the fingerprint must cover could not be listed or read.
#[derive(Debug)]
pub enum FingerprintError {
    Walk(walkdir::Error),
    NonUtf8Path(std::path::PathBuf),
    OutsideRoot(std::path::PathBuf),
    Read(std::path::PathBuf, std::io::Error),
}

impl fmt::Display for FingerprintError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Walk(error) => write!(formatter, "cannot list project files: {error}"),
            Self::NonUtf8Path(path) => write!(formatter, "path is not UTF-8: {}", path.display()),
            Self::OutsideRoot(path) => {
                write!(formatter, "path is outside the project: {}", path.display())
            }
            Self::Read(path, error) => write!(formatter, "cannot read {}: {error}", path.display()),
        }
    }
}
