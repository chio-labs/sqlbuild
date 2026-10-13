//! Rejections of `sqb diff` requests and inputs.

/// A rejected diff request or input: message, `C` code and optional help.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DiffUserError {
    pub message: String,
    pub code: String,
    pub help: Option<String>,
}
