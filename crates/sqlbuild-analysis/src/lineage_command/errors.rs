//! User-facing `sqb lineage` failures.

/// A CLI user error: its code, message and optional help.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct LineageError {
    pub code: &'static str,
    pub message: String,
    pub help: Option<String>,
}

impl LineageError {
    /// An error without help text.
    #[must_use]
    pub fn new(code: &'static str, message: &str) -> Self {
        Self {
            code,
            message: message.to_owned(),
            help: None,
        }
    }

    /// The same error with help text.
    #[must_use]
    pub fn with_help(self, help: &str) -> Self {
        Self {
            help: Some(help.to_owned()),
            ..self
        }
    }
}
