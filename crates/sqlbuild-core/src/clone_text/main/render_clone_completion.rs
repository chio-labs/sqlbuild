//! The final clone output: non-success messages, then the completion line with counts.

use crate::cli_text::main::format_completion_line::format_completion_line;
use crate::cli_text::main::format_summary_footer::format_summary_footer;
use crate::cli_text::models::{CliStyle, CompletionState, SummaryCount};
use crate::clone_text::constants::{ACTION_SUMMARY, STATUS_SUMMARY};
use crate::clone_text::models::{CloneItemText, CloneStatusKind};

fn count(items: &[CloneItemText], predicate: impl Fn(&CloneItemText) -> bool) -> i64 {
    i64::try_from(items.iter().filter(|item| predicate(item)).count()).unwrap_or(i64::MAX)
}

/// Messages of items that did not succeed, a blank line, and the completion summary.
#[must_use]
pub fn render_clone_completion(
    items: &[CloneItemText],
    elapsed_seconds: Option<f64>,
    style: CliStyle,
) -> String {
    let mut text: String = String::new();
    for item in items {
        if let (Some(message), false) = (&item.message, item.status == CloneStatusKind::Success) {
            text.push_str(&format!(
                "  {}  {}\n",
                style.object_name(&item.name),
                style.muted(message)
            ));
        }
    }
    let mut counts: Vec<SummaryCount> = ACTION_SUMMARY
        .iter()
        .map(|(label, action)| SummaryCount {
            label: (*label).to_owned(),
            value: count(items, |item| item.action == *action),
        })
        .collect();
    counts.extend(STATUS_SUMMARY.iter().map(|(label, status)| SummaryCount {
        label: (*label).to_owned(),
        value: count(items, |item| item.status == *status),
    }));
    counts.push(SummaryCount {
        label: "TOTAL".to_owned(),
        value: count(items, |_| true),
    });
    let elapsed: Option<String> = elapsed_seconds.map(|seconds| format!("{seconds:.2}s"));
    let footer: String = format_summary_footer(style, &counts, elapsed.as_deref());
    let warnings: i64 = count(items, |item| item.status == CloneStatusKind::Warning);
    let failures: i64 = count(items, |item| item.status == CloneStatusKind::Failed);
    let (state, label) = match (warnings, failures) {
        (0, 0) => (CompletionState::Ok, "Completed successfully"),
        (_, 0) => (CompletionState::Warn, "Completed with warnings"),
        _ => (CompletionState::Fail, "Completed with errors"),
    };
    text.push('\n');
    text.push_str(&format_completion_line(style, state, label, Some(&footer)));
    text.push('\n');
    text
}
