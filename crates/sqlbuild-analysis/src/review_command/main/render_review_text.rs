//! The review summary printed at the end of a terminal run.

use crate::review_command::_helpers::sections::{
    baseline_lines, changed_lines, context_line, headline, impact_tree, incomplete_lines,
    run_lines, tests_lines,
};
use crate::review_command::_helpers::text::{PLAIN, block, count_pairs, finding_lines};
use crate::review_command::models::ReviewReport;

/// The plain-text review: findings and changes first, then impact, coverage, tests and run details.
#[must_use]
pub fn render_review_text(report: &ReviewReport) -> String {
    let checks: [String; 2] = if report.dry_run {
        [String::new(), String::new()]
    } else {
        [
            block("Baseline", &baseline_lines(report, PLAIN)),
            block("Tests and audits", &tests_lines(report)),
        ]
    };
    [
        block("Findings", &finding_lines(report)),
        block("What changed", &changed_lines(report, PLAIN)),
        block("Downstream impact", &impact_tree(report, PLAIN)),
        block("Incomplete coverage", &incomplete_lines(report, PLAIN)),
        checks.concat(),
        block("Run details", &run_lines(report, PLAIN)),
        format!(
            "\n{}  {}\n{}\n",
            headline(report),
            count_pairs(report),
            context_line(report, PLAIN)
        ),
    ]
    .concat()
}
