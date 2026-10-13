//! Invalid janitor settings.

/// A CLI user error: its code and message.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct JanitorSettingsError {
    pub code: &'static str,
    pub message: &'static str,
}
