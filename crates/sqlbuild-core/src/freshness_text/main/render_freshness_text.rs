//! The human output of `sqb freshness`.

use crate::cli_text::main::format_summary_footer::format_summary_footer;
use crate::cli_text::models::{CliStyle, SummaryCount};
use crate::freshness_text::_helpers::counts::{age_count, status_count};
use crate::freshness_text::_helpers::detail::detail;
use crate::freshness_text::constants::{
    AGE_SUMMARY, GROUPS, STATUS_SUMMARY, TREE_BRANCH_GLYPH, TREE_LAST_GLYPH,
};
use crate::freshness_text::models::FreshnessSourceResult;

/// Sources grouped by status, the status counts, and the age policy counts when any apply.
#[must_use]
pub fn render_freshness_text(results: &[FreshnessSourceResult], style: CliStyle) -> String {
    let mut lines: Vec<String> = vec![style.title("Source freshness")];
    let width: usize = results
        .iter()
        .map(|result| result.name.chars().count())
        .max()
        .unwrap_or(0);
    for (status, title) in GROUPS {
        let group: Vec<&FreshnessSourceResult> = results
            .iter()
            .filter(|result| result.status == status)
            .collect();
        if group.is_empty() {
            continue;
        }
        lines.push(String::new());
        lines.push(style.section(&format!("{title} ({})", group.len())));
        for (index, result) in group.iter().enumerate() {
            let connector: String = style.muted(if index + 1 == group.len() {
                TREE_LAST_GLYPH
            } else {
                TREE_BRANCH_GLYPH
            });
            let padding: String = " ".repeat(width.saturating_sub(result.name.chars().count()));
            let detail: String = detail(result, style);
            let suffix: String = if detail.is_empty() {
                String::new()
            } else {
                format!("  {detail}")
            };
            lines.push(format!(
                "{connector} {}{suffix}",
                style.object_name(&format!("{}{padding}", result.name))
            ));
        }
    }
    lines.push(String::new());
    let counts: Vec<SummaryCount> = STATUS_SUMMARY
        .iter()
        .map(|(label, _, status)| SummaryCount {
            label: (*label).to_owned(),
            value: status_count(results, *status),
        })
        .collect();
    lines.push(format_summary_footer(style, &counts, None));
    if results.iter().any(|result| result.age_status.is_some()) {
        let ages: Vec<SummaryCount> = AGE_SUMMARY
            .iter()
            .map(|(label, _, age)| SummaryCount {
                label: (*label).to_owned(),
                value: age_count(results, age),
            })
            .collect();
        lines.push(format!(
            "{}  {}",
            style.section("Age policy"),
            format_summary_footer(style, &ages, None)
        ));
    }
    format!("{}\n", lines.join("\n"))
}
