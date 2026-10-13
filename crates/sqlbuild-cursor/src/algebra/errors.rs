//! Cursor algebra failures, each the exception Python raises for the same input.

use std::fmt::{self, Display};

/// A failed cursor operation and the Python exception class that reports it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum CursorError {
    /// `CursorAlgebraError`: values that cannot form a valid typed interval.
    Algebra(String),
    /// `OverflowError` from `datetime` or `timedelta` arithmetic.
    Overflow(String),
    /// `ValueError` from `date.replace`.
    Value(String),
    /// `TypeError` from ordering keys of different kinds.
    Type(String),
}

impl Display for CursorError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(match self {
            Self::Algebra(message)
            | Self::Overflow(message)
            | Self::Value(message)
            | Self::Type(message) => message,
        })
    }
}

impl std::error::Error for CursorError {}
