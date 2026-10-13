//! Audit outcome counts as the summary reports them.

/// How many audits ended in each outcome.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct AuditCounts {
    pub passed: usize,
    pub warned: usize,
    pub failed: usize,
    pub insufficient: usize,
    pub total: usize,
}
