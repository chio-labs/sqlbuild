//! Why relation-name extraction fails.

/// The wheel's `ValueError` for an unknown dialect, or an internal native failure.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RelationNamesFailure {
    UnknownDialect(String),
    Internal(String),
}
