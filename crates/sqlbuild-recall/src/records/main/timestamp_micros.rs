//! `timestamp_micros`: Recall timestamp text as microseconds since the epoch.

use crate::records::_helpers::time::parse_micros;

/// The microseconds of an ISO-8601 UTC timestamp, `None` when `text` is not one.
#[must_use]
pub fn timestamp_micros(text: &str) -> Option<i64> {
    parse_micros(text)
}
