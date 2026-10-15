//! ISO text of UTC instants as Python's `datetime.isoformat` writes them.

use crate::execution_history::constants::UTC_OFFSET_TEXT;
use crate::execution_history::types::UtcTime;

/// `value.isoformat(timespec="microseconds")` of a UTC `datetime`.
pub(crate) fn stored_text(value: &UtcTime) -> String {
    format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}.{:06}{UTC_OFFSET_TEXT}",
        value.date.year,
        value.date.month,
        value.date.day,
        value.hour,
        value.minute,
        value.second,
        value.microsecond
    )
}

/// `value.isoformat()` of a UTC `datetime`: microseconds only when non-zero.
pub(crate) fn default_text(value: &UtcTime) -> String {
    if value.microsecond != 0 {
        return stored_text(value);
    }
    format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}{UTC_OFFSET_TEXT}",
        value.date.year, value.date.month, value.date.day, value.hour, value.minute, value.second
    )
}
