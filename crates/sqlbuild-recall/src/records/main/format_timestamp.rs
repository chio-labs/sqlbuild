//! `format_timestamp`: a system time as Recall stores it.

use std::time::SystemTime;

use crate::records::_helpers::time::{format_micros, system_micros};

/// `YYYY-MM-DDTHH:MM:SS.ffffffZ` in UTC.
#[must_use]
pub fn format_timestamp(time: SystemTime) -> String {
    format_micros(system_micros(time))
}
