//! Clone item results as the command renders them.

/// The outcome of one cloned resource.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CloneStatusKind {
    Success,
    Warning,
    Failed,
}

impl CloneStatusKind {
    /// The status from its value, treating anything unknown as success.
    #[must_use]
    pub fn from_value(value: &str) -> Self {
        match value {
            "warning" => Self::Warning,
            "failed" => Self::Failed,
            _ => Self::Success,
        }
    }
}

/// One clone item result.
#[derive(Clone, Debug, PartialEq)]
pub struct CloneItemText {
    pub name: String,
    /// The `CloneAction` value, such as `copied`.
    pub action: String,
    pub status: CloneStatusKind,
    pub message: Option<String>,
    pub origin_relation: Option<String>,
    pub destination_relation: Option<String>,
    pub duration_seconds: Option<f64>,
}

/// Fingerprint propagation progress: confirmed count, total, and identities still pending.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct FingerprintProgress {
    pub completed: i64,
    pub total: i64,
    pub pending_identities: Vec<String>,
}
