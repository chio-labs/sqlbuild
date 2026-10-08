//! Outcome of the native cursor intrinsic check.

/// Whether Python accepts SQL as intrinsic-free, rejects it with this error, or must decide.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum IntrinsicCheck {
    Free,
    Rejected(String),
    Deferred,
}
