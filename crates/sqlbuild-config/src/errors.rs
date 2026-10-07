//! Structured failures of reading configuration files.

/// Why a configuration document could not be loaded natively.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ConfigErrorKind {
    /// The text is not a valid document; Python's parser rejects it too.
    Syntax,
    /// The document parses but a value cannot be built, as PyYAML's constructor or `tomllib` reports.
    Construct,
    /// The document uses a feature the native reader leaves to Python.
    Unsupported,
    /// A required file does not exist.
    Missing,
    /// A field SQLBuild reads has the wrong type or an invalid value.
    InvalidField,
}

/// A configuration failure; the Python reader re-parses the file to report its exact message.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ConfigError {
    pub kind: ConfigErrorKind,
    pub message: String,
    pub line: Option<usize>,
    pub column: Option<usize>,
}

impl ConfigError {
    /// An error without a position.
    pub fn new(kind: ConfigErrorKind, message: impl Into<String>) -> Self {
        Self {
            kind,
            message: message.into(),
            line: None,
            column: None,
        }
    }
}
