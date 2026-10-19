//! Why a Recall store operation failed.

/// What kind of failure a store reported.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum StoreErrorKind {
    /// The file or directory cannot be created or written.
    Permission,
    /// Another writer holds the lock past the busy timeout; retrying may succeed.
    Busy,
    /// The file is not a SQLite database, or its pages are damaged.
    Corrupt,
    /// The SQLite library is older than the store needs.
    Version,
    /// A query was rejected: not read-only, or invalid SQL.
    Query,
    /// No invocation matches.
    NotFound,
    /// More than one invocation matches.
    Ambiguous,
    Other,
}

/// A store failure with its kind and message.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct StoreError {
    pub kind: StoreErrorKind,
    pub message: String,
}

impl StoreError {
    pub(crate) fn new(kind: StoreErrorKind, message: impl Into<String>) -> Self {
        Self {
            kind,
            message: message.into(),
        }
    }
}

impl std::fmt::Display for StoreError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl std::error::Error for StoreError {}
