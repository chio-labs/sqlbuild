//! Formatter selector errors.

use std::fmt;

/// A selector or positional path names a path outside every formatter-owned folder.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FormatSelectorError {
    pub message: String,
    pub code: &'static str,
    pub help: Option<String>,
}

impl fmt::Display for FormatSelectorError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl std::error::Error for FormatSelectorError {}
