//! Why the explicit-reference checks stop.

/// The error Python's checks raise, or an internal native failure.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ReferenceFailure {
    /// `CompileInputError(message)`: a Python hook reads an unknown resource.
    CompileInput(String),
    /// The relation-name parse's `ValueError` for an unknown dialect.
    UnknownDialect(String),
    Internal(String),
}
