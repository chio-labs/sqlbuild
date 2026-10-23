//! The review as a Markdown document for a pull request.

use crate::review_command::_helpers::markdown::{
    MARKDOWN, evidence, findings, impact, section, summary_table,
};
use crate::review_command::_helpers::sections::{
    baseline_lines, changed_lines, context_line, has_evidence, headline, incomplete_lines,
    run_lines, tests_lines,
};
use crate::review_command::models::{NodeReport, ReviewReport};

/// The review as Markdown: outcome, summary, findings, changes, impact, coverage and run details.
#[must_use]
pub fn render_review_markdown(report: &ReviewReport) -> String {
    let evidence_nodes: Vec<&NodeReport> = report
        .nodes
        .iter()
        .filter(|node| has_evidence(node))
        .collect();
    [
        format!(
            "# {}\n\n{}\n\n",
            headline(report),
            context_line(report, MARKDOWN)
        ),
        summary_table(report),
        findings(report),
        section(
            "What changed",
            &changed_lines(report, MARKDOWN),
            "No definition changes.",
        ),
        impact(report),
        section(
            "Incomplete coverage",
            &incomplete_lines(report, MARKDOWN),
            "Every check completed.",
        ),
        section(
            "Baseline",
            &baseline_lines(report, MARKDOWN),
            "No baseline.",
        ),
        section(
            "Tests and audits",
            &tests_lines(report),
            "No tests or audits ran.",
        ),
        evidence(&evidence_nodes, &report.baseline.against),
        section("Run details", &run_lines(report, MARKDOWN), ""),
    ]
    .concat()
}
