//! Rules configuration that a project's own policy rejects.

/// A configuration policy violation, with help showing the setting to change.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ConfigPolicyError {
    pub message: String,
    pub help: String,
}
