//! The audit summary footer.

use crate::audit_command::models::AuditCounts;
use crate::cli_text::main::format_summary_footer::format_summary_footer;
use crate::cli_text::models::{CliStyle, SummaryCount};

fn count(label: &str, value: usize) -> SummaryCount {
    SummaryCount {
        label: label.to_owned(),
        value: i64::try_from(value).unwrap_or(i64::MAX),
    }
}

/// A blank line and the PASS, WARN, FAIL, INSUFFICIENT and TOTAL counts.
#[must_use]
pub fn render_audit_summary(counts: AuditCounts, style: CliStyle) -> String {
    format!(
        "\n{}\n",
        format_summary_footer(
            style,
            &[
                count("PASS", counts.passed),
                count("WARN", counts.warned),
                count("FAIL", counts.failed),
                count("INSUFFICIENT", counts.insufficient),
                count("TOTAL", counts.total),
            ],
            None,
        )
    )
}
