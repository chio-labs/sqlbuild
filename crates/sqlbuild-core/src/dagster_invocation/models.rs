//! Values of Dagster invocation assembly.

/// The display facts of one incomplete asset in an execution document.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct AssetFailure {
    pub kind: String,
    pub name: String,
    pub status: String,
    pub failed_phase: Option<String>,
    pub error_message: Option<String>,
    pub error_code: Option<String>,
    pub staging_relation: Option<String>,
    pub failed_sql: Option<String>,
    pub last_recorded_sql: Option<String>,
}
