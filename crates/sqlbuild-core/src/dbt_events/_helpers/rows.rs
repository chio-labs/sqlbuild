//! Node row columns: counter, status label and truncated text.

use crate::dbt_events::constants::DISPLAY_STATUSES;
use crate::dbt_events::models::{DbtNodeResult, DbtRowPosition};

/// The stream counter, else dbt's index and total, else the stream index alone.
pub(crate) fn counter(result: &DbtNodeResult, position: DbtRowPosition) -> String {
    if let (Some(index), Some(total)) = (position.display_index, position.display_total) {
        return format!("{index}/{total}");
    }
    if let (Some(index), Some(total)) = (result.index, result.total) {
        return format!("{index}/{total}");
    }
    position
        .display_index
        .map_or_else(|| "-".to_owned(), |index| index.to_string())
}

/// The label for a dbt status, else the status upper-cased.
pub(crate) fn display_status(status: &str) -> String {
    let normalized: String = status.to_lowercase();
    DISPLAY_STATUSES
        .iter()
        .find(|(statuses, _)| statuses.contains(&normalized.as_str()))
        .map_or_else(|| status.to_uppercase(), |(_, label)| (*label).to_owned())
}

/// The first `width` characters.
pub(crate) fn truncated(text: &str, width: usize) -> String {
    text.chars().take(width).collect()
}
