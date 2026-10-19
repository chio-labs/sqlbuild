//! Recall setting value parsing: durations, retention days and strings.

use crate::models::ConfigValue;
use crate::recall::constants::{
    DECIMAL_RADIX, HOURS_PER_DAY, MAX_RETENTION_DAYS, MAX_SHUTDOWN_TIMEOUT_MS, MILLIS_PER_SECOND,
};

/// The unsigned decimal before `unit`, `None` when it is not one or overflows.
fn amount(text: &str, unit: &str) -> Option<u64> {
    let digits = text.strip_suffix(unit)?;
    if digits.is_empty() {
        return None;
    }
    digits.bytes().try_fold(0_u64, |total, byte| {
        let digit = char::from(byte).to_digit(DECIMAL_RADIX)?;
        total
            .checked_mul(u64::from(DECIMAL_RADIX))?
            .checked_add(u64::from(digit))
    })
}

/// Whole days of `30d` or `720h`, within the supported range.
pub(crate) fn retention_days(text: &str) -> Option<u32> {
    let days = amount(text, "d").or_else(|| {
        amount(text, "h")
            .filter(|hours| hours % HOURS_PER_DAY == 0)
            .map(|hours| hours / HOURS_PER_DAY)
    })?;
    if days == 0 || days > MAX_RETENTION_DAYS {
        return None;
    }
    Some(u32::try_from(days).unwrap_or(u32::MAX))
}

/// Milliseconds of `3s` or `500ms`, within the supported range.
pub(crate) fn timeout_ms(text: &str) -> Option<u64> {
    let millis = amount(text, "ms")
        .or_else(|| amount(text, "s").and_then(|seconds| seconds.checked_mul(MILLIS_PER_SECOND)))?;
    (millis <= MAX_SHUTDOWN_TIMEOUT_MS).then_some(millis)
}

/// A non-negative TOML integer of bytes; `None` for anything else.
pub(crate) fn output_bytes(value: &ConfigValue) -> Option<u64> {
    match value {
        ConfigValue::Integer(bytes) if *bytes >= 0 => Some(bytes.unsigned_abs()),
        _ => None,
    }
}

/// A trimmed non-empty string, or the message for `label.key`.
pub(crate) fn non_empty<'a>(
    value: &'a ConfigValue,
    label: &str,
    key: &str,
) -> Result<&'a str, String> {
    match value {
        ConfigValue::String(text) if !text.trim().is_empty() => Ok(text.trim()),
        _ => Err(format!("{label}.{key} must be a non-empty string")),
    }
}
