//! Compute log storage rejections, each naming the Python `ComputeLogStorageError` subclass.

use std::io;

/// Which `sqlbuild.runtime.compute_logs.exceptions` class a rejection raises.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ComputeLogErrorKind {
    InvalidCaptureId,
    InvalidCursor,
    InvalidLimit,
    AlreadyExists,
    NotFound,
    State,
    Path,
    Metadata,
}

/// A storage rejection with its message, or an operating system failure Python lets propagate.
#[derive(Debug)]
pub enum ComputeLogError {
    Rejected(ComputeLogErrorKind, String),
    Io(io::Error),
}

impl ComputeLogError {
    /// A rejection of `kind` with `message`.
    pub fn rejected(kind: ComputeLogErrorKind, message: impl Into<String>) -> Self {
        Self::Rejected(kind, message.into())
    }
}

impl From<io::Error> for ComputeLogError {
    fn from(error: io::Error) -> Self {
        Self::Io(error)
    }
}
