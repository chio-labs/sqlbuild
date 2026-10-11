//! Python's `isinstance`, truth, ordering and equality over loaded values.

use crate::constants::FEBRUARY;
use crate::models::{ConfigDateTime, ConfigValue};
use crate::project::constants::ZERO_FLOAT;
use std::cmp::Ordering;

const SECONDS_PER_DAY: i64 = 86_400;
const SECONDS_PER_HOUR: i64 = 3_600;
const SECONDS_PER_MINUTE: i64 = 60;
const MICROSECONDS_PER_SECOND: i64 = 1_000_000;

/// `isinstance(value, int)`, which includes booleans.
pub(crate) fn is_int(value: &ConfigValue) -> bool {
    matches!(
        value,
        ConfigValue::Integer(_) | ConfigValue::BigInteger(_) | ConfigValue::Bool(_)
    )
}

/// `value < bound` for a Python integer `value`.
pub(crate) fn int_below(value: &ConfigValue, bound: i64) -> bool {
    match value {
        ConfigValue::Integer(number) => *number < bound,
        ConfigValue::Bool(flag) => i64::from(*flag) < bound,
        ConfigValue::BigInteger(text) => text.starts_with('-'),
        _ => false,
    }
}

/// `bool(value)`.
pub(crate) fn is_truthy(value: &ConfigValue) -> bool {
    match value {
        ConfigValue::Null => false,
        ConfigValue::Bool(flag) => *flag,
        ConfigValue::Integer(number) => *number != 0,
        ConfigValue::Float(number) => *number != ZERO_FLOAT,
        ConfigValue::String(text) => !text.is_empty(),
        ConfigValue::List(items) => !items.is_empty(),
        ConfigValue::Map(entries) => !entries.is_empty(),
        ConfigValue::BigInteger(_)
        | ConfigValue::Date(_)
        | ConfigValue::DateTime(_)
        | ConfigValue::Time(_) => true,
    }
}

/// The exact decimal digits of an integral number, signed, or `None` for any other value.
fn integral_text(value: &ConfigValue) -> Option<String> {
    match value {
        ConfigValue::Bool(flag) => Some(i64::from(*flag).to_string()),
        ConfigValue::Integer(number) => Some(number.to_string()),
        ConfigValue::BigInteger(text) => Some(text.clone()),
        ConfigValue::Float(number) if *number == ZERO_FLOAT => Some("0".to_owned()),
        ConfigValue::Float(number) if number.is_finite() && number.fract() == ZERO_FLOAT => {
            Some(format!("{number:.0}"))
        }
        _ => None,
    }
}

fn is_number(value: &ConfigValue) -> bool {
    is_int(value) || matches!(value, ConfigValue::Float(_))
}

/// `left == right` between Python numbers, comparing exactly as Python does.
fn numbers_equal(left: &ConfigValue, right: &ConfigValue) -> bool {
    match (left, right) {
        (ConfigValue::Float(first), ConfigValue::Float(second)) => first == second,
        _ => integral_text(left).is_some() && integral_text(left) == integral_text(right),
    }
}

/// Microseconds since the epoch-free origin of an aware datetime, in UTC.
fn utc_microseconds(moment: &ConfigDateTime, offset: i32) -> i128 {
    let days = days_from_civil(
        i64::from(moment.date.year),
        i64::from(moment.date.month),
        i64::from(moment.date.day),
    );
    let seconds = days * SECONDS_PER_DAY
        + i64::from(moment.time.hour) * SECONDS_PER_HOUR
        + i64::from(moment.time.minute) * SECONDS_PER_MINUTE
        + i64::from(moment.time.second)
        - i64::from(offset);
    i128::from(seconds) * i128::from(MICROSECONDS_PER_SECOND) + i128::from(moment.time.microsecond)
}

/// Days from 0000-03-01 to a proleptic Gregorian date.
fn days_from_civil(year: i64, month: i64, day: i64) -> i64 {
    let shifted = if month <= FEBRUARY { year - 1 } else { year };
    let era = shifted.div_euclid(400);
    let year_of_era = shifted - era * 400;
    let month_index = (month + 9) % 12;
    let day_of_year = (153 * month_index + 2) / 5 + day - 1;
    let day_of_era = year_of_era * 365 + year_of_era / 4 - year_of_era / 100 + day_of_year;
    era * 146_097 + day_of_era
}

fn datetimes_equal(left: &ConfigDateTime, right: &ConfigDateTime) -> bool {
    match (left.utc_offset_seconds, right.utc_offset_seconds) {
        (None, None) => left == right,
        (Some(first), Some(second)) => {
            utc_microseconds(left, first) == utc_microseconds(right, second)
        }
        _ => false,
    }
}

fn entry_equal(entry: &(ConfigValue, ConfigValue), right: &[(ConfigValue, ConfigValue)]) -> bool {
    let (key, value) = entry;
    for (candidate, other) in right {
        if python_equal(candidate, key) {
            return python_equal(value, other);
        }
    }
    false
}

fn maps_equal(left: &[(ConfigValue, ConfigValue)], right: &[(ConfigValue, ConfigValue)]) -> bool {
    left.len() == right.len() && left.iter().all(|entry| entry_equal(entry, right))
}

/// `left == right` with Python's semantics for the loaded value domain.
pub(crate) fn python_equal(left: &ConfigValue, right: &ConfigValue) -> bool {
    if is_number(left) && is_number(right) {
        return numbers_equal(left, right);
    }
    match (left, right) {
        (ConfigValue::Null, ConfigValue::Null) => true,
        (ConfigValue::String(first), ConfigValue::String(second)) => first == second,
        (ConfigValue::Date(first), ConfigValue::Date(second)) => first == second,
        (ConfigValue::Time(first), ConfigValue::Time(second)) => first == second,
        (ConfigValue::DateTime(first), ConfigValue::DateTime(second)) => {
            datetimes_equal(first, second)
        }
        (ConfigValue::List(first), ConfigValue::List(second)) => {
            first.len() == second.len()
                && first
                    .iter()
                    .zip(second)
                    .all(|(item, other)| python_equal(item, other))
        }
        (ConfigValue::Map(first), ConfigValue::Map(second)) => maps_equal(first, second),
        _ => false,
    }
}

/// Compare two non-negative decimal digit strings without leading zeros.
pub(crate) fn compare_naturals(left: &str, right: &str) -> Ordering {
    left.len().cmp(&right.len()).then_with(|| left.cmp(right))
}
