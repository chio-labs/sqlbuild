//! Check selection errors.

/// A selection that resolved to Python nodes other than checks.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CheckSelectionError {
    pub code: &'static str,
    pub message: String,
}
