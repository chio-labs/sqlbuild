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

/// The display facts of one failed check (audit, SQL test or Python check) in an execution document.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct FailedCheck {
    pub kind: String,
    pub name: String,
    pub asset_name: Option<String>,
    pub column_name: Option<String>,
    pub status: String,
    pub row_count: Option<i64>,
}
