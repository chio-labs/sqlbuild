//! Scenario command usage errors.

/// A user error the CLI reports with its code and optional help.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ScenarioCommandError {
    pub code: &'static str,
    pub message: String,
    pub help: Option<String>,
}
