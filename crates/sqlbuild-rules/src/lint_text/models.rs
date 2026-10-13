//! Interpolation sites, suppression outcomes and fixture-null candidates.

/// One interpolation occurrence replaced by a sentinel; offsets are character positions.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct InterpolationSite {
    pub sentinel: String,
    pub neutralized_start: usize,
    pub neutralized_end: usize,
    pub original_start: usize,
    pub original_end: usize,
    pub original_text: String,
}

/// Text with its interpolation replaced by sentinels, and the replaced sites in order.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Neutralized {
    pub text: String,
    pub sites: Vec<InterpolationSite>,
}

/// The identity of one existing violation that a suppression can remove.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SuppressibleViolation {
    pub file: usize,
    pub line: usize,
    pub code: String,
    pub native: bool,
}

/// One valid directive: its code, its line and the line it suppresses.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SuppressionDirective {
    pub code: String,
    pub line: usize,
    pub target: usize,
}

/// A suppression finding on one directive line; offsets are character positions.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SuppressionFinding {
    pub file: usize,
    pub line: usize,
    pub message: String,
    pub remediation: &'static str,
    pub fault: bool,
    pub fix: Option<(usize, usize)>,
    pub fix_unavailable_reason: Option<&'static str>,
}

/// One retained violation: an input violation by index, or a new suppression finding.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum RetainedViolation {
    Existing(usize),
    Added(SuppressionFinding),
}

/// SQL-test files that may hold removable typed nulls, and the models their fixtures stand in for.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct FixtureNullCandidates {
    pub paths: Vec<String>,
    pub model_names: Vec<String>,
}
