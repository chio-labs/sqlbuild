//! Whether authored config contains a construct, or that only Python can tell.

/// The answer Python's recursive config scan gives, or a deferral to that scan.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Presence {
    Present,
    Absent,
    /// A string needs Python's Unicode `\s` class to decide.
    Deferred,
}

/// Where Python's config walk first finds a macro call.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum MacroPath {
    /// The mapping keys leading to the first string holding a macro call.
    Found(Vec<String>),
    Absent,
    /// A string before any match needs Python's Unicode rules to decide.
    Deferred,
}
