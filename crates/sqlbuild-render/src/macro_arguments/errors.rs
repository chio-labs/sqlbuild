//! Why one macro call's arguments cannot be used.

/// Why the arguments cannot be used, where, and how to fix them.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ArgumentError {
    /// What is wrong, completing "Macro arguments in '<file>' ...".
    pub detail: String,
    pub help: String,
    /// 1-based line and column, in characters, within the argument text.
    pub line: usize,
    pub column: usize,
}
