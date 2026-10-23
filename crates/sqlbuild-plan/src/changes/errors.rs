//! Planner change-detection errors.

/// A `replay_on_change` value that is not a known policy.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct UnknownReplayPolicy(pub String);

impl UnknownReplayPolicy {
    /// The planner input error message.
    pub fn message(&self) -> String {
        format!("unknown replay_on_change '{}'", self.0)
    }
}
