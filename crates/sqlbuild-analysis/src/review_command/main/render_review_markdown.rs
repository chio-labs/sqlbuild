//! The review as a Markdown document for a pull request.

use crate::review_command::_helpers::sections::{
    Style, baseline_lines, changed_lines, context_line, example_lines, finding_text, has_evidence,
    headline, impact_tree, incomplete_lines, run_lines, summary_counts, tests_lines,
};
use crate::review_command::_helpers::wording::counted;
use crate::review_command::models::{NodeComparison, NodeReport, ReviewReport};

const STYLE: Style = Style { markdown: true };

fn cell(text: &str) -> String {
    text.replace('|', "\\|").replace('\n', " ")
}

fn bullets(out: &mut String, lines: &[String]) {
    for line in lines {
        out.push_str(&format!("- {line}\n"));
    }
}

fn section(out: &mut String, title: &str, lines: &[String], empty: &str) {
    out.push_str(&format!("\n## {title}\n\n"));
    if lines.is_empty() {
        out.push_str(&format!("{empty}\n"));
    } else {
        bullets(out, lines);
    }
}

fn evidence_rows(comparison: &NodeComparison) -> Vec<[String; 5]> {
    let mut rows: Vec<[String; 5]> = Vec::new();
    for column in &comparison.added_columns {
        rows.push([
            column.clone(),
            "column".into(),
            "absent".into(),
            "added".into(),
            "exact match".into(),
        ]);
    }
    for column in &comparison.removed_columns {
        rows.push([
            column.clone(),
            "column".into(),
            "present".into(),
            "removed".into(),
            "exact match".into(),
        ]);
    }
    for (column, target, branch) in &comparison.type_changes {
        rows.push([
            column.clone(),
            "type".into(),
            target.clone(),
            branch.clone(),
            "exact match".into(),
        ]);
    }
    for column in &comparison.columns {
        rows.push([
            column.column.clone(),
            column.metric.clone(),
            column.target.clone(),
            column.branch.clone(),
            column.limit.clone(),
        ]);
    }
    rows
}

fn evidence(out: &mut String, node: &NodeReport, against: &str) {
    let Some(comparison) = &node.comparison else {
        return;
    };
    let rows: Vec<[String; 5]> = evidence_rows(comparison);
    out.push_str(&format!(
        "\n<details><summary>{}: {}</summary>\n\n",
        cell(&node.name),
        counted(rows.len(), "difference", "differences")
    ));
    if !rows.is_empty() {
        out.push_str(&format!(
            "| Column | Metric | {} | branch | Limit |\n",
            cell(against)
        ));
        out.push_str("|---|---|---|---|---|\n");
        for row in &rows {
            let cells: Vec<String> = row.iter().map(|text| cell(text)).collect();
            out.push_str(&format!("| {} |\n", cells.join(" | ")));
        }
        out.push('\n');
    }
    let rows_text: String = match (comparison.target_rows, comparison.branch_rows) {
        (Some(target), Some(branch)) => format!("rows {against} {target}, branch {branch}; "),
        _ => String::new(),
    };
    out.push_str(&format!(
        "{rows_text}{} compared with no difference ({} comparison).\n\n</details>\n",
        counted(
            comparison.unchanged_columns,
            "other column",
            "other columns"
        ),
        comparison.mode.replace('_', " ")
    ));
}

/// The review as Markdown: outcome, summary, findings, changes, impact, coverage and run details.
#[must_use]
pub fn render_review_markdown(report: &ReviewReport) -> String {
    let against: &str = &report.baseline.against;
    let mut out: String = format!(
        "# {}\n\n{}\n\n",
        headline(report),
        context_line(report, STYLE)
    );
    let counts: Vec<(&str, usize)> = summary_counts(report);
    let labels: Vec<&str> = counts.iter().map(|(label, _)| *label).collect();
    out.push_str(&format!("| {} |\n", labels.join(" | ")));
    out.push_str(&format!("|{}\n", "---:|".repeat(counts.len())));
    let values: Vec<String> = counts.iter().map(|(_, count)| count.to_string()).collect();
    out.push_str(&format!("| {} |\n", values.join(" | ")));
    out.push_str("\n## Findings\n\n");
    if report.findings.is_empty() {
        out.push_str("No findings.\n");
    }
    for (index, finding) in report.findings.iter().enumerate() {
        out.push_str(&format!(
            "{}. {}\n",
            index + 1,
            finding_text(finding, against, STYLE)
        ));
        for example in example_lines(finding, STYLE) {
            out.push_str(&format!("   - {example}\n"));
        }
    }
    section(
        &mut out,
        "What changed",
        &changed_lines(report, STYLE),
        "No definition changes.",
    );
    out.push_str("\n## Downstream impact\n\n");
    let tree: Vec<String> = impact_tree(report, Style { markdown: false });
    if tree.is_empty() {
        out.push_str("No changed models or seeds.\n");
    } else {
        out.push_str("```text\n");
        for line in tree {
            out.push_str(&format!("{line}\n"));
        }
        out.push_str("```\n");
    }
    section(
        &mut out,
        "Incomplete coverage",
        &incomplete_lines(report, STYLE),
        "Every check completed.",
    );
    section(
        &mut out,
        "Baseline",
        &baseline_lines(report, STYLE),
        "No baseline.",
    );
    section(
        &mut out,
        "Tests and audits",
        &tests_lines(report),
        "No tests or audits ran.",
    );
    let evidence_nodes: Vec<&NodeReport> = report
        .nodes
        .iter()
        .filter(|node| has_evidence(node))
        .collect();
    if !evidence_nodes.is_empty() {
        out.push_str("\n## Per-model evidence\n");
        for node in evidence_nodes {
            evidence(&mut out, node, against);
        }
    }
    section(&mut out, "Run details", &run_lines(report, STYLE), "");
    out
}
