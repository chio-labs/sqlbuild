//! One validated Recall settings table; absent keys inherit.

/// The settings one `[recall]` or `targets.<name>.recall` table sets.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct RecallSection {
    pub enabled: Option<bool>,
    pub connection: Option<String>,
    pub retention_days: Option<u32>,
    pub shutdown_timeout_ms: Option<u64>,
    pub diagnostics_min_severity: Option<String>,
    /// Bytes of each output stream to record; `Some(0)` records everything.
    pub max_output_bytes: Option<u64>,
}
