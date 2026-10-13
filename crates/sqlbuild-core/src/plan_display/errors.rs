//! Plan display errors.

/// A cursor grain outside the known grains.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct UnknownCursorGrain(pub String);
