//! Selector failures.

/// Python's `PlannerInputError` for a selector: code, message and optional help.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SelectorError {
    pub code: &'static str,
    pub message: String,
    pub help: Option<String>,
}
