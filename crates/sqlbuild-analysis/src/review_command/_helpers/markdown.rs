//! The blocks of the Markdown review, each rendered on its own.

use crate::review_command::_helpers::sections::{
    Style, example_lines, finding_text, impact_tree, summary_counts,
};
use crate::review_command::_helpers::wording::counted;
use crate::review_command::models::{NodeComparison, NodeReport, ReviewReport};

pub(crate) const MARKDOWN: Style = Style { markdown: true };
const PLAIN: Style = Style { markdown: false };

/// One row of the per-model evidence table.
struct EvidenceRow {
    column: String,
    metric: String,
    target: String,
    branch: String,
    limit: String,
}

impl EvidenceRow {
    fn exact(column: &str, metric: &str, (target, branch): (&str, &str)) -> Self {
        Self {
            column: column.to_owned(),
            metric: metric.to_owned(),
            target: target.to_owned(),
            branch: branch.to_owned(),
            limit: "exact match".to_owned(),
        }
    }

    fn cells(&self) -> [&str; 5] {
        [
            &self.column,
            &self.metric,
            &self.target,
            &self.branch,
            &self.limit,
        ]
    }
}

fn cell(text: &str) -> String {
    text.replace('|', "\\|").replace('\n', " ")
}

/// A `## title` section listing `lines`, or `empty` when there are none.
pub(crate) fn section(title: &str, lines: &[String], empty: &str) -> String {
    let body: String = if lines.is_empty() {
        format!("{empty}\n")
    } else {
        lines.iter().map(|line| format!("- {line}\n")).collect()
    };
    format!("\n## {title}\n\n{body}")
}

/// The one-row summary table of counts.
pub(crate) fn summary_table(report: &ReviewReport) -> String {
    let counts: Vec<(&str, usize)> = summary_counts(report);
    let labels: Vec<&str> = counts.iter().map(|(label, _)| *label).collect();
    let values: Vec<String> = counts.iter().map(|(_, count)| count.to_string()).collect();
    format!(
        "| {} |\n|{}\n| {} |\n",
        labels.join(" | "),
        "---:|".repeat(counts.len()),
        values.join(" | ")
    )
}

/// The numbered findings with their example keys.
pub(crate) fn findings(report: &ReviewReport) -> String {
    let against: &str = &report.baseline.against;
    if report.findings.is_empty() {
        return "\n## Findings\n\nNo findings.\n".to_owned();
    }
    let mut lines: Vec<String> = Vec::new();
    for (index, finding) in report.findings.iter().enumerate() {
        lines.push(format!(
            "{}. {}\n",
            index + 1,
            finding_text(finding, against, MARKDOWN)
        ));
        lines.extend(
            example_lines(finding, MARKDOWN)
                .into_iter()
                .map(|example| format!("   - {example}\n")),
        );
    }
    format!("\n## Findings\n\n{}", lines.concat())
}

/// The lineage tree of the changed set in a fenced block.
pub(crate) fn impact(report: &ReviewReport) -> String {
    let tree: Vec<String> = impact_tree(report, PLAIN);
    if tree.is_empty() {
        return "\n## Downstream impact\n\nNo changed models or seeds.\n".to_owned();
    }
    let lines: String = tree.iter().map(|line| format!("{line}\n")).collect();
    format!("\n## Downstream impact\n\n```text\n{lines}```\n")
}

fn evidence_rows(comparison: &NodeComparison) -> Vec<EvidenceRow> {
    let added = comparison
        .added_columns
        .iter()
        .map(|column| EvidenceRow::exact(column, "column", ("absent", "added")));
    let removed = comparison
        .removed_columns
        .iter()
        .map(|column| EvidenceRow::exact(column, "column", ("present", "removed")));
    let retyped = comparison
        .type_changes
        .iter()
        .map(|(column, target, branch)| EvidenceRow::exact(column, "type", (target, branch)));
    let values = comparison.columns.iter().map(|column| EvidenceRow {
        column: column.column.clone(),
        metric: column.metric.clone(),
        target: column.target.clone(),
        branch: column.branch.clone(),
        limit: column.limit.clone(),
    });
    added.chain(removed).chain(retyped).chain(values).collect()
}

fn table_row(row: &EvidenceRow) -> String {
    let cells: Vec<String> = row.cells().iter().map(|text| cell(text)).collect();
    format!("| {} |\n", cells.join(" | "))
}

fn evidence_table(rows: &[EvidenceRow], against: &str) -> String {
    if rows.is_empty() {
        return String::new();
    }
    let body: String = rows.iter().map(table_row).collect();
    format!(
        "| Column | Metric | {} | branch | Limit |\n|---|---|---|---|---|\n{body}\n",
        cell(against)
    )
}

/// One collapsed block of the columns that changed in one model.
fn node_evidence(node: &NodeReport, comparison: &NodeComparison, against: &str) -> String {
    let rows: Vec<EvidenceRow> = evidence_rows(comparison);
    let rows_text: String = match (comparison.target_rows, comparison.branch_rows) {
        (Some(target), Some(branch)) => format!("rows {against} {target}, branch {branch}; "),
        _ => String::new(),
    };
    format!(
        "\n<details><summary>{}: {}</summary>\n\n{}{rows_text}{} compared with no difference ({} comparison).\n\n</details>\n",
        cell(&node.name),
        counted(rows.len(), "difference", "differences"),
        evidence_table(&rows, against),
        counted(
            comparison.unchanged_columns,
            "other column",
            "other columns"
        ),
        comparison.mode.replace('_', " ")
    )
}

fn compared_evidence(node: &NodeReport, against: &str) -> Option<String> {
    let comparison: &NodeComparison = node.comparison.as_ref()?;
    Some(node_evidence(node, comparison, against))
}

/// The per-model evidence of every node whose comparison found a difference.
pub(crate) fn evidence(nodes: &[&NodeReport], against: &str) -> String {
    let blocks: String = nodes
        .iter()
        .filter_map(|node| compared_evidence(node, against))
        .collect();
    if blocks.is_empty() {
        return String::new();
    }
    format!("\n## Per-model evidence\n{blocks}")
}
