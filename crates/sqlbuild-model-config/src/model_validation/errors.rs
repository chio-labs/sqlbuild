//! Why native config parsing rejects a value.

/// Why `fromisoformat` raises `ValueError`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum IsoError {
    /// `Invalid isoformat string: <repr>`.
    InvalidString,
    /// Any other `ValueError` message.
    Message(String),
}

/// A duration Python reads but SQLBuild rejects.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum DurationNumberError {
    /// An amount uses digits outside ASCII.
    NonAsciiDigits,
    /// An amount does not fit in a signed 64-bit integer.
    TooLarge,
}
