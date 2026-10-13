//! Build command user errors.

/// A user error the CLI reports with its optional code and help.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct BuildCommandError {
    pub code: Option<String>,
    pub message: String,
    pub help: Option<String>,
}

impl BuildCommandError {
    /// An error with an optional code and help.
    #[must_use]
    pub fn new(code: Option<&str>, message: String, help: Option<&str>) -> Self {
        Self {
            code: code.map(str::to_owned),
            message,
            help: help.map(str::to_owned),
        }
    }
}
