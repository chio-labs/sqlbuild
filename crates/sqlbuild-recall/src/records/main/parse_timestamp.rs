//! `parse_timestamp`: a stored or ISO-8601 UTC timestamp as a system time.

use std::time::{Duration, SystemTime, UNIX_EPOCH};

use crate::records::_helpers::time::parse_micros;

/// The time of `text`, or `None` when it is not a UTC ISO-8601 timestamp.
#[must_use]
pub fn parse_timestamp(text: &str) -> Option<SystemTime> {
    let micros = parse_micros(text)?;
    let magnitude = Duration::from_micros(micros.unsigned_abs());
    if micros >= 0 {
        UNIX_EPOCH.checked_add(magnitude)
    } else {
        UNIX_EPOCH.checked_sub(magnitude)
    }
}
