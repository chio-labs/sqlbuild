//! One rules finding and the counts a rules result reports.

/// One rules finding; `path` is the project-relative POSIX path.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct RuleFinding {
    pub code: String,
    pub path: String,
    pub line: i64,
    pub column: i64,
    pub message: String,
    pub remediation: String,
    pub unevaluated: bool,
    pub affected_rules: Vec<String>,
    pub fixable: bool,
}

/// The model, resource and cache counts of one rules result.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct ResultCounts {
    pub evaluated_models: i64,
    pub unevaluated_resources: i64,
    pub cache_hits: i64,
    pub cache_misses: i64,
}
