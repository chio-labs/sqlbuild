//! Failures resolving a command's connection or warehouse.

/// A command connection failure, raised as the Python exception its kind names.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum CommandConnectionError {
    /// `CliUserError(message, code=code, help=help)`.
    User {
        code: Option<&'static str>,
        message: String,
        help: Option<String>,
    },
    /// `ProjectConfigError(message)`.
    ProjectConfig(String),
}

impl CommandConnectionError {
    /// The message the raised exception carries.
    #[must_use]
    pub fn message(&self) -> &str {
        match self {
            Self::User { message, .. } | Self::ProjectConfig(message) => message,
        }
    }
}
