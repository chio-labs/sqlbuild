//! The review summary printed at the end of a terminal run.

use crate::review_command::_helpers::sections::{
    Style, baseline_lines, changed_lines, context_line, example_lines, finding_text, headline,
    impact_tree, incomplete_lines, run_lines, summary_counts, tests_lines,
};

use crate::review_command::models::ReviewReport;

const STYLE: Style = Style { markdown: false };

fn block(out: &mut String, title: &str, lines: &[String]) {
    if lines.is_empty() {
        return;
    }
    out.push_str(&format!("\n{title}\n"));
    for line in lines {
        out.push_str(&format!("  {line}\n"));
    }
}

/// The plain-text review: findings and changes first, then impact, coverage, tests and run details.
#[must_use]
pub fn render_review_text(report: &ReviewReport) -> String {
    let against: &str = &report.baseline.against;
    let mut out: String = String::new();
    let counts: Vec<String> = summary_counts(report)
        .iter()
        .map(|(label, count)| format!("{}={count}", label.to_ascii_lowercase().replace(' ', "_")))
        .collect();
    let mut findings: Vec<String> = Vec::new();
    for (index, finding) in report.findings.iter().enumerate() {
        findings.push(format!(
            "{}. {}",
            index + 1,
            finding_text(finding, against, STYLE)
        ));
        for example in example_lines(finding, STYLE) {
            findings.push(format!("   {example}"));
        }
    }
    block(&mut out, "Findings", &findings);
    block(&mut out, "What changed", &changed_lines(report, STYLE));
    block(&mut out, "Downstream impact", &impact_tree(report, STYLE));
    block(
        &mut out,
        "Incomplete coverage",
        &incomplete_lines(report, STYLE),
    );
    if !report.dry_run {
        block(&mut out, "Baseline", &baseline_lines(report, STYLE));
        block(&mut out, "Tests and audits", &tests_lines(report));
    }
    block(&mut out, "Run details", &run_lines(report, STYLE));
    out.push_str(&format!(
        "\n{}  {}\n{}\n",
        headline(report),
        counts.join("  "),
        context_line(report, STYLE)
    ));
    out
}
