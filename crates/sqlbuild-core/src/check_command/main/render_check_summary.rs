//! The check summary footer.

use crate::check_command::models::{CheckResultText, CheckStatus};
use crate::cli_text::main::format_summary_footer::format_summary_footer;
use crate::cli_text::models::{CliStyle, SummaryCount};

fn count(results: &[CheckResultText], status: Option<CheckStatus>) -> i64 {
    let matched: usize = results
        .iter()
        .filter(|result| status.is_none_or(|status| result.status == status))
        .count();
    i64::try_from(matched).unwrap_or(i64::MAX)
}

/// A blank line and the PASS, WARN, FAIL and TOTAL counts.
#[must_use]
pub fn render_check_summary(results: &[CheckResultText], style: CliStyle) -> String {
    let counts: Vec<SummaryCount> = [
        ("PASS", Some(CheckStatus::Pass)),
        ("WARN", Some(CheckStatus::Warn)),
        ("FAIL", Some(CheckStatus::Fail)),
        ("TOTAL", None),
    ]
    .into_iter()
    .map(|(label, status)| SummaryCount {
        label: label.to_owned(),
        value: count(results, status),
    })
    .collect();
    format!("\n{}\n", format_summary_footer(style, &counts, None))
}
