//! The names a refactoring looks for in Python string constants.

/// Renamed names, and the name a SQL-like string must also mention, if any.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct StringQuery<'a> {
    pub names: &'a [String],
    pub context: Option<&'a str>,
}
