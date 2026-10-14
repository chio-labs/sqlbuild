//! Cost summary facts a delayed refresh compares.

/// The status and statement coverage of one persisted or refreshed cost summary.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct CostCoverage {
    pub status: String,
    pub expected_statement_count: i64,
    pub observed_statement_count: i64,
    pub query_count: i64,
    pub limitations: Vec<String>,
}
