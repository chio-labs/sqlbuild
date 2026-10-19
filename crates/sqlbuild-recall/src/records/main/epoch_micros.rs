//! `epoch_micros`: a system time as microseconds since the epoch.

use std::time::SystemTime;

use crate::records::_helpers::time::system_micros;

/// Microseconds since the epoch; times before it count back.
#[must_use]
pub fn epoch_micros(time: SystemTime) -> i64 {
    system_micros(time)
}
