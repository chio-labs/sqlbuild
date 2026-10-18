//! The whole seconds of a fixed duration such as `90s` or `1h30m`.

use crate::model_validation::_helpers::durations::parse_duration;

/// The duration's seconds, or `None` when it does not parse or includes months or years.
#[must_use]
pub fn fixed_duration_seconds(text: &str) -> Option<u128> {
    match parse_duration(text) {
        Ok(Some(duration)) if duration.total_months == 0 => Some(duration.fixed_seconds),
        Ok(_) | Err(_) => None,
    }
}
