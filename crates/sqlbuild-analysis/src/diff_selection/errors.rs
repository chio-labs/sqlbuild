//! A diff selector that resolves to nothing, as Python's `PlannerInputError` reports it.

/// The message and code of a rejected selector.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SelectorError {
    pub message: String,
    pub code: &'static str,
}
