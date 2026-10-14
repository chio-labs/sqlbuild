//! One completed standalone audit row.

use crate::build_progress::models::AuditResultText;
use crate::cli_text::models::CliStyle;
use crate::nested_progress::constants::{
    AUDIT_NAME_WIDTH, ERROR_OUTCOME, LABEL_WIDTH, PASS_OUTCOME, WARN_OUTCOME,
};

/// The audit name and column, status, failing row count and optional duration.
#[must_use]
pub fn render_audit_row(
    result: &AuditResultText,
    duration_ms: Option<f64>,
    style: CliStyle,
) -> String {
    let status_text: &str = match result.outcome.as_str() {
        PASS_OUTCOME => "PASS",
        WARN_OUTCOME => "WARN",
        ERROR_OUTCOME => "FAIL",
        _ => "INSUFFICIENT",
    };
    let name: String = match &result.attached_column_name {
        Some(column) => format!("{} ({column})", result.audit_name),
        None => result.audit_name.clone(),
    };
    let mut detail: String = String::new();
    if result.outcome != PASS_OUTCOME && result.row_count > 0 {
        let label: &str = if result.row_count == 1 { "row" } else { "rows" };
        detail = format!("  {} {label}", result.row_count);
    }
    if let Some(duration_ms) = duration_ms {
        detail = format!("{detail}  {:.2}s", duration_ms / 1000.0);
    }
    format!(
        "    {:<LABEL_WIDTH$}{name:<AUDIT_NAME_WIDTH$} {}{detail}\n",
        "audit",
        style.status(status_text)
    )
}
