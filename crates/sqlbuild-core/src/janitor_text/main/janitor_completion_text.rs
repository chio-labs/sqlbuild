//! The summary of a completed janitor run.

use crate::cli_text::main::format_count_noun::format_count_noun;
use crate::cli_text::models::CliStyle;
use crate::janitor_text::models::JanitorResultCounts;

fn noun(count: usize, singular: &str) -> String {
    format_count_noun(i64::try_from(count).unwrap_or(i64::MAX), singular, None)
}

/// `[Archived N relations. ]Deleted M objects[ and pruned K direct state tables].`
#[must_use]
pub fn janitor_completion_text(counts: &JanitorResultCounts, style: CliStyle) -> String {
    let archived: String = if counts.archived == 0 {
        String::new()
    } else {
        format!("Archived {}. ", noun(counts.archived, "relation"))
    };
    let objects: String = noun(
        counts.deleted
            + counts.deleted_archives
            + counts.deleted_query_artifacts
            + counts.dropped_old_name_views,
        "object",
    );
    let deleted: String = if counts.pruned_direct_state == 0 {
        format!("Deleted {objects}.")
    } else {
        format!(
            "Deleted {objects} and pruned {}.",
            noun(counts.pruned_direct_state, "direct state table")
        )
    };
    format!("{}\n", style.success(&format!("{archived}{deleted}")))
}
