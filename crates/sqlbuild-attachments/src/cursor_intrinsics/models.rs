//! Outcome of the native cursor intrinsic check.

/// Whether SQL is free of cursor intrinsics, or Python must decide (and usually raise).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum IntrinsicCheck {
    Free,
    Deferred,
}
