//! The log record fields a `--debug` console line shows.

/// The fields of one Python log record a diagnostics console line shows.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct DiagnosticRecordText {
    pub level_name: String,
    pub logger_name: String,
    pub message: String,
    /// `sqlbuild_subject`, `sqlbuild_name` and `sqlbuild_event` when they are strings.
    pub subject: Option<String>,
    pub name: Option<String>,
    pub event: Option<String>,
    /// Each `label=value` context token whose record field is a string, in display order.
    pub tokens: Vec<(&'static str, String)>,
    /// `sqlbuild_duration_ms / 1000` when the field is an integer, as Python divides it.
    pub duration_seconds: Option<f64>,
    /// `sqlbuild_sql` when it is a string.
    pub sql: Option<String>,
}
