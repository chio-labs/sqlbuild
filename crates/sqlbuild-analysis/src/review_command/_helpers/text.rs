//! The blocks of the terminal review summary.

use crate::review_command::_helpers::sections::{
    Style, example_lines, finding_text, summary_counts,
};
use crate::review_command::models::ReviewReport;

pub(crate) const PLAIN: Style = Style { markdown: false };

/// A titled block of indented lines, or nothing when there are none.
pub(crate) fn block(title: &str, lines: &[String]) -> String {
    if lines.is_empty() {
        return String::new();
    }
    let body: String = lines.iter().map(|line| format!("  {line}\n")).collect();
    format!("\n{title}\n{body}")
}

/// The numbered findings, each followed by its example keys.
pub(crate) fn finding_lines(report: &ReviewReport) -> Vec<String> {
    let against: &str = &report.baseline.against;
    let mut lines: Vec<String> = Vec::new();
    for (index, finding) in report.findings.iter().enumerate() {
        lines.push(format!(
            "{}. {}",
            index + 1,
            finding_text(finding, against, PLAIN)
        ));
        lines.extend(
            example_lines(finding, PLAIN)
                .into_iter()
                .map(|example| format!("   {example}")),
        );
    }
    lines
}

/// `label=count` pairs of the summary counts.
pub(crate) fn count_pairs(report: &ReviewReport) -> String {
    summary_counts(report)
        .iter()
        .map(|(label, count)| format!("{}={count}", label.to_ascii_lowercase().replace(' ', "_")))
        .collect::<Vec<String>>()
        .join("  ")
}
