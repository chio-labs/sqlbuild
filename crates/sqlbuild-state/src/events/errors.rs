//! Failures rendering one state event row.

use std::fmt::{self, Display};

/// A value whose kind does not fit its declared state column, with Python's message.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct StateSqlError(pub String);

impl Display for StateSqlError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.0)
    }
}

impl std::error::Error for StateSqlError {}
