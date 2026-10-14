//! Failures of the authored-SQL text transforms.

use std::fmt;

/// A lint text transform could not complete.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum LintTextError {
    /// A formatted body no longer holds exactly one of each sentinel.
    Restoration(String),
    /// A built-in pattern failed to compile.
    Pattern(String),
}

impl fmt::Display for LintTextError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Restoration(message) | Self::Pattern(message) => formatter.write_str(message),
        }
    }
}

impl std::error::Error for LintTextError {}
