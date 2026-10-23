//! The user errors that stop review planning.

/// A user error that stops planning.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ReviewPlanError {
    pub code: String,
    pub message: String,
    pub help: Option<String>,
}
