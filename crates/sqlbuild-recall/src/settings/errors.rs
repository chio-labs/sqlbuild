//! Why Recall settings cannot be resolved.

/// A settings problem, with a message naming the setting.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SettingsError {
    pub message: String,
    /// A configuration mistake every command reports, such as an unknown or incomplete connection; an unset environment variable or unreachable store is not one.
    pub invalid_configuration: bool,
}

impl SettingsError {
    pub(crate) fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
            invalid_configuration: false,
        }
    }

    pub(crate) fn invalid_configuration(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
            invalid_configuration: true,
        }
    }
}

impl std::fmt::Display for SettingsError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl std::error::Error for SettingsError {}
