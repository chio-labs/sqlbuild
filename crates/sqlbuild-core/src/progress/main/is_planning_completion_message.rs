//! Whether a planning progress message completes its phase.

use crate::progress::constants::PLANNING_COMPLETION_PREFIXES;

/// Completion messages start with a past-tense verb such as `Planned ` or `Compiled `.
#[must_use]
pub fn is_planning_completion_message(message: &str) -> bool {
    PLANNING_COMPLETION_PREFIXES
        .iter()
        .any(|prefix| message.starts_with(prefix))
}
