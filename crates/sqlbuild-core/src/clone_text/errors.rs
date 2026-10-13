//! Clone request validation errors.

/// A clone request the targets do not allow, with its diagnostic code.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CloneTargetError {
    pub code: &'static str,
    pub message: String,
}
