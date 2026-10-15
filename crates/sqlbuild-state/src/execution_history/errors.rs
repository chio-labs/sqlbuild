//! Execution history rejections, each naming the Python `ExecutionHistoryStorageError` subclass.

/// Which `sqlbuild.runtime.execution_history.exceptions` class a rejection raises.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum HistoryErrorKind {
    Storage,
    IntegrityConflict,
    InvalidEvent,
    InvalidCursor,
    InvalidFilter,
    InvalidLimit,
    UnsupportedSchemaVersion,
    ProjectionConsistency,
}

/// One rejection and its message.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct HistoryError {
    pub kind: HistoryErrorKind,
    pub message: String,
}

impl HistoryError {
    /// A rejection of `kind` with `message`.
    pub fn new(kind: HistoryErrorKind, message: impl Into<String>) -> Self {
        Self {
            kind,
            message: message.into(),
        }
    }
}
