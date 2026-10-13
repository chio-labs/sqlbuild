//! Source freshness failures, each the exception Python raises for the same input.

use std::fmt::{self, Display};

/// A failed freshness decision and the Python exception class that reports it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum FreshnessError {
    /// `SourceFreshnessObservationError`.
    Observation(String),
    /// `SourceFreshnessInputError`.
    Input(String),
    /// `OverflowError` from building a `timedelta`.
    Overflow(String),
}

impl Display for FreshnessError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(match self {
            Self::Observation(message) | Self::Input(message) | Self::Overflow(message) => message,
        })
    }
}

impl std::error::Error for FreshnessError {}
