//! Python dictionary key semantics for constructed YAML mappings.

use crate::constants::FEBRUARY;
use crate::models::{ConfigDateTime, ConfigValue};
use crate::yaml::constants::{SECONDS_PER_DAY, SECONDS_PER_MINUTE};

/// Whether Python can hash the value, so it can be a dictionary key.
pub(crate) fn is_hashable(value: &ConfigValue) -> bool {
    !matches!(value, ConfigValue::List(_) | ConfigValue::Map(_))
}

/// The exact integer text of an integral float, or `None` for fractions and non-finite floats.
fn integral_float_text(value: f64) -> Option<String> {
    let integral = value.is_finite() && value.trunc() == value;
    integral.then(|| format!("{:.0}", value + 0.0))
}

/// Numeric keys as exact integer text where Python would compare them as equal integers.
fn integer_text(value: &ConfigValue) -> Option<String> {
    match value {
        ConfigValue::Bool(flag) => Some(u8::from(*flag).to_string()),
        ConfigValue::Integer(number) => Some(number.to_string()),
        ConfigValue::BigInteger(text) => Some(text.clone()),
        ConfigValue::Float(number) => integral_float_text(*number),
        _ => None,
    }
}

fn day_number(value: &ConfigDateTime) -> i64 {
    let (year, month, day) = (
        i64::from(value.date.year),
        i64::from(value.date.month),
        i64::from(value.date.day),
    );
    let shifted_year = if month <= FEBRUARY { year - 1 } else { year };
    let era_day = (153 * ((month + 9) % 12) + 2) / 5 + day - 1;
    shifted_year * 365 + shifted_year / 4 - shifted_year / 100 + shifted_year / 400 + era_day
}

fn instant(value: &ConfigDateTime) -> (i64, u32) {
    let seconds = day_number(value) * i64::from(SECONDS_PER_DAY)
        + i64::from(value.time.hour) * 3600
        + i64::from(value.time.minute) * i64::from(SECONDS_PER_MINUTE)
        + i64::from(value.time.second)
        - i64::from(value.utc_offset_seconds.unwrap_or_default());
    (seconds, value.time.microsecond)
}

/// Text equal for two hashable keys exactly when Python's `==` holds, as `1 == 1.0 == True`.
pub(crate) fn key_identity(value: &ConfigValue) -> String {
    if let Some(integer) = integer_text(value) {
        return format!("int:{integer}");
    }
    match value {
        ConfigValue::String(text) => format!("str:{text}"),
        ConfigValue::Float(number) if number.is_nan() => "float:nan".to_owned(),
        ConfigValue::Float(number) => format!("float:{}", number.to_bits()),
        ConfigValue::DateTime(moment) if moment.utc_offset_seconds.is_some() => {
            format!("aware:{:?}", instant(moment))
        }
        other => format!("{other:?}"),
    }
}
