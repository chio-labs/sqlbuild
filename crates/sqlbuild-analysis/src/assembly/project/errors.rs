//! The errors Python's resource assembly raises.

/// The error Python's resource assembly raises.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AssemblyError {
    /// `CompileInputError(message, help=help)`.
    CompileInput {
        message: String,
        help: Option<String>,
    },
    /// `ValueError(message)`.
    Value(String),
    /// The exception the request holds at this index, raised as is.
    Raise(usize),
    /// An internal native failure.
    Internal(String),
}
