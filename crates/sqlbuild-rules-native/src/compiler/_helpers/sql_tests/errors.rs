//! Error types owned by SQL-test planning helpers.

use std::fmt::Display;

use serde::ser;

/// A parsed statement that `serde_json::to_value` could not represent.
#[derive(Debug)]
pub(crate) struct RelationMarkerError;

impl Display for RelationMarkerError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str("value cannot be represented as JSON")
    }
}

impl std::error::Error for RelationMarkerError {}

impl ser::Error for RelationMarkerError {
    fn custom<M: Display>(_message: M) -> Self {
        RelationMarkerError
    }
}
