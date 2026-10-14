//! A cursor bound as plans and progress rows show it.

use crate::plan_display::constants::{INTEGER_CURSOR, WHOLE_DAY_CURSOR_GRAINS};
use crate::plan_display::models::ParsedBound;

/// The value, collapsed to its date when a whole-day grain bound falls at midnight.
#[must_use]
pub fn cursor_bound_display(
    value: &str,
    (cursor_type, cursor_grain): (Option<&str>, Option<&str>),
    parsed: Option<&ParsedBound>,
) -> String {
    if cursor_type == Some(INTEGER_CURSOR) {
        return value.to_owned();
    }
    match parsed {
        Some(bound)
            if bound.midnight
                && cursor_grain.is_some_and(|grain| WHOLE_DAY_CURSOR_GRAINS.contains(&grain)) =>
        {
            bound.date.clone()
        }
        _ => value.to_owned(),
    }
}
