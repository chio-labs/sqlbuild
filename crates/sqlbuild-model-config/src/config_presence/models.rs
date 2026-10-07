//! Whether authored config contains a construct, or that only Python can tell.

/// The answer Python's recursive config scan gives, or a deferral to that scan.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Presence {
    Present,
    Absent,
    /// A string needs Python's Unicode `\s` class to decide.
    Deferred,
}
