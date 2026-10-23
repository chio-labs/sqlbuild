//! The final line of a janitor run.

use crate::cli_text::main::format_completion_line::format_completion_line;
use crate::cli_text::models::{CliStyle, CompletionState};
use crate::janitor_text::_helpers::phases::duration;
use crate::janitor_text::models::JanitorResultCounts;

/// `✓ Janitor completed  archived N, deleted M, pruned K  (5m 02s)`, or `✗ Janitor failed  ...`.
#[must_use]
pub fn render_janitor_completion(
    counts: &JanitorResultCounts,
    elapsed_seconds: Option<f64>,
    failed: bool,
    style: CliStyle,
) -> String {
    let deleted: usize = counts.deleted
        + counts.deleted_archives
        + counts.deleted_query_artifacts
        + counts.dropped_review_schemas
        + counts.dropped_old_name_views;
    let mut summary: String = [
        ("archived", counts.archived),
        ("deleted", deleted),
        ("pruned", counts.pruned_direct_state),
    ]
    .iter()
    .map(|(label, count)| format!("{label} {}", style.value(&count.to_string())))
    .collect::<Vec<String>>()
    .join(", ");
    if let Some(seconds) = elapsed_seconds {
        summary.push_str(&format!(
            "  {}",
            style.muted(&format!("({})", duration(seconds)))
        ));
    }
    let (state, label) = if failed {
        (CompletionState::Fail, "Janitor failed")
    } else {
        (CompletionState::Ok, "Janitor completed")
    };
    format!(
        "{}\n",
        format_completion_line(style, state, label, Some(&summary))
    )
}
