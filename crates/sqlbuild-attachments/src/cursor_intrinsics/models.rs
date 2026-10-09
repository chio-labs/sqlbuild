//! Outcome of the native cursor intrinsic check.

/// Whether SQL is free of cursor intrinsics, or the error rejecting it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum IntrinsicCheck {
    Free,
    Rejected(String),
}
