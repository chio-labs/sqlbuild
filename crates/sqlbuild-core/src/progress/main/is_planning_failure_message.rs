//! Whether a planning progress message ends its phase with a failure.

use crate::progress::constants::PLANNING_FAILURE_PREFIXES;

/// Failure messages start with `Failed `, as in `Failed runtime cursor watermark ...`.
#[must_use]
pub fn is_planning_failure_message(message: &str) -> bool {
    PLANNING_FAILURE_PREFIXES
        .iter()
        .any(|prefix| message.starts_with(prefix))
}
