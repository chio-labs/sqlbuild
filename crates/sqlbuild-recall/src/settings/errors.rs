//! Why Recall settings cannot be resolved.

/// A settings problem, with a message naming the setting.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SettingsError {
    pub message: String,
}

impl SettingsError {
    pub(crate) fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

impl std::fmt::Display for SettingsError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl std::error::Error for SettingsError {}
