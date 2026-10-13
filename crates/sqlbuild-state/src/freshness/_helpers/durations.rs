//! Single-unit minute, hour or day durations, as `Duration.parse` and `fixed_seconds` read them.

use sqlbuild_cursor::algebra::main::parse_duration::parse_duration;
use sqlbuild_cursor::algebra::models::DurationDigits;

use crate::freshness::constants::{SECONDS_PER_DAY, SECONDS_PER_HOUR, SECONDS_PER_MINUTE};

/// Seconds of a duration; `None` inside `Some` when they exceed `u128`.
pub(crate) type DurationSeconds = Option<u128>;

fn is_zero(digits: &str) -> bool {
    digits.bytes().all(|byte| byte == b'0')
}

/// The seconds of `text` when it names exactly one of minutes, hours or days.
pub(crate) fn single_unit_seconds(text: &str) -> Option<DurationSeconds> {
    let digits: DurationDigits = parse_duration(text)?;
    let fixed: [(&str, u128); 3] = [
        (&digits.days, SECONDS_PER_DAY),
        (&digits.hours, SECONDS_PER_HOUR),
        (&digits.minutes, SECONDS_PER_MINUTE),
    ];
    let calendar_or_seconds: bool =
        !is_zero(&digits.years) || !is_zero(&digits.months) || !is_zero(&digits.seconds);
    let mut used = fixed.iter().filter(|(amount, _)| !is_zero(amount));
    let (amount, unit) = used.next()?;
    if calendar_or_seconds || used.next().is_some() {
        return None;
    }
    let Ok(value) = amount.parse::<u128>() else {
        return Some(None);
    };
    Some(value.checked_mul(*unit))
}
