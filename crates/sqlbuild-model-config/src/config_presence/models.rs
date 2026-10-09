//! Where a config walk finds a macro call.

/// Where Python's config walk first finds a macro call.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum MacroPath {
    /// The mapping keys leading to the first string holding a macro call.
    Found(Vec<String>),
    Absent,
}
