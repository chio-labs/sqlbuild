//! Why a model's column reads could not be resolved at all.

/// A failure Python's resolution raised rather than treating as unparseable SQL.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum RequiredColumnsError {
    /// Polyglot does not know the dialect; Python's `ValueError`.
    UnknownDialect(String),
    /// Analysis normalization rejected the SQL; Python's `ValueError`.
    Normalization(String),
}
