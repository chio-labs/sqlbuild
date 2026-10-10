//! Why type normalization fails.

/// Why Python's `normalize_type` raises instead of returning a type.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TypeNormalizationError {
    /// Polyglot does not know the dialect name: the wheel's `ValueError`.
    UnknownDialect(String),
    /// Polyglot cannot write the parsed type back as SQL: the wheel's `PolyglotError`.
    Generation(String),
}

impl TypeNormalizationError {
    /// The message Python's exception carries.
    #[must_use]
    pub fn message(&self) -> String {
        match self {
            Self::UnknownDialect(name) => format!("Unknown dialect: {name}"),
            Self::Generation(message) => message.clone(),
        }
    }
}
