//! Build result facts and their aggregate counts.

/// The status, error code, warning count and audit outcomes of one model result.
#[derive(Debug, Clone, Default)]
pub struct ModelResultFacts {
    pub status: String,
    pub error_code: Option<String>,
    pub warning_count: usize,
    pub audit_outcomes: Vec<String>,
}

/// The statuses and outcomes of every result one build produced.
#[derive(Debug, Clone, Default)]
pub struct BuildResultFacts {
    pub models: Vec<ModelResultFacts>,
    pub seed_statuses: Vec<String>,
    /// `(status, warning count)` of each function result.
    pub functions: Vec<(String, usize)>,
    pub load_statuses: Vec<String>,
    pub test_outcomes: Vec<String>,
    pub source_audit_outcomes: Vec<String>,
    pub end_audit_outcomes: Vec<String>,
}

/// Aggregate counts and whether the build failed.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct BuildCounts {
    pub success: usize,
    pub failure: usize,
    pub skipped: usize,
    pub warning: usize,
    pub insufficient: usize,
    pub failed: bool,
}
