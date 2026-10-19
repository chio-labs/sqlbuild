//! Rules configuration that a project's own policy rejects.

/// A configuration policy violation, with help showing the setting to change.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ConfigPolicyError {
    pub message: String,
    pub help: String,
}

/// Why a project's rules configuration cannot be loaded.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum RulesConfigLoadError {
    /// The configuration is unreadable or malformed.
    Invalid(String),
    /// The configuration uses a setting SQLBuild rejects, with help showing the fix.
    Policy(ConfigPolicyError),
}
