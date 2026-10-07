//! Why stored bytes could not be read back.

/// Stored bytes end early, carry unknown fields or were written by another format.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct StoreDecodeError;
