//! Expected cost command errors and their CLI codes.

/// A refused cost request: its CLI error code and message.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CostCommandError {
    pub code: &'static str,
    pub message: String,
}

impl CostCommandError {
    #[must_use]
    pub fn new(code: &'static str, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
        }
    }
}
