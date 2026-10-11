//! Why per-query column analysis outside the session fails.

/// A query Python's normalization rejects (its `ValueError`), or an internal native failure.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum QueryColumnsFailure {
    Normalization(String),
    Internal(String),
}
