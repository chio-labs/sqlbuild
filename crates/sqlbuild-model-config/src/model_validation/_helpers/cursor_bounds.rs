//! `cursor_start` and `cursor_end` checks with the errors Python raises, and their ordering keys.

use std::cmp::Ordering;

use crate::model_validation::_helpers::config::ConfigView;
use crate::model_validation::_helpers::config::model_header_help;
use crate::model_validation::_helpers::decimals::{DecimalText, FiniteDecimal, decimal_text};
use crate::model_validation::_helpers::isoformat::{
    IsoDateTime, datetime_fromisoformat, epoch_micros, local_micros, supported_micros,
    utc_isoformat,
};
use crate::model_validation::constants::{INTEGER_CURSOR, TIMESTAMP_CURSOR};
use crate::model_validation::errors::IsoError;
use crate::model_validation::models::ValidationStop;
use crate::model_validation::types::Check;
use crate::types::{AuthoredNode, NodeKind};

const MICROS_PER_SECOND: i64 = 1_000_000;

/// A bound's `_cursor_contract_key`, or the overflow Python reports while shifting it to UTC.
pub(crate) enum BoundKey {
    /// `Decimal(str(value))` of an integer cursor.
    Integer(FiniteDecimal),
    /// `Decimal(str(utc.timestamp()))`: the float seconds since the Unix epoch.
    Timestamp(f64),
    /// The UTC shift leaves years 1-9999; the text is the value's ISO form at UTC.
    Overflow(String),
}

/// Check one bound as `_validate_timestamp_cursor_start` or `_validate_integer_cursor_start` does.
pub(crate) fn check_bound<N: AuthoredNode>(
    config: &ConfigView<'_, N>,
    bound: &N,
    cursor_type: Option<&str>,
) -> Check {
    match cursor_type {
        Some(TIMESTAMP_CURSOR) => check_timestamp_bound(config, bound),
        Some(INTEGER_CURSOR) => check_integer_bound(config, bound),
        _ => Ok(()),
    }
}

fn check_timestamp_bound<N: AuthoredNode>(config: &ConfigView<'_, N>, bound: &N) -> Check {
    if bound.is_date_like() {
        return Ok(());
    }
    let Some(text) = bound.text() else {
        return Err(config
            .error("cursor_start for cursor_type=timestamp must be a string or date-like value"));
    };
    match datetime_fromisoformat(&text, config.python.minor_version()) {
        Ok(_) => Ok(()),
        Err(error) => {
            let reason: String = match error {
                IsoError::InvalidString => {
                    format!("Invalid isoformat string: {}", bound.python_repr())
                }
                IsoError::Message(message) => message,
            };
            Err(config.error(format!(
                "cursor_start value '{text}' is not a valid ISO timestamp: {reason}"
            )))
        }
    }
}

fn check_integer_bound<N: AuthoredNode>(config: &ConfigView<'_, N>, bound: &N) -> Check {
    match bound.kind() {
        NodeKind::Bool(_) => {
            Err(config.error("cursor_start for cursor_type=integer must be an integer"))
        }
        NodeKind::Int { .. } if bound.integer().is_none() => {
            Err(config.integer_too_large("cursor_start", bound))
        }
        NodeKind::Int { .. } => Ok(()),
        NodeKind::Str => {
            let text: String = bound.text().unwrap_or_default();
            match decimal_text(config.python, &text) {
                DecimalText::Finite(decimal) if decimal.is_integral() => Ok(()),
                DecimalText::Finite(_) => {
                    Err(config.error(format!("cursor_start value '{text}' is not a whole number")))
                }
                DecimalText::NonAsciiDigit => Err(ValidationStop::Error(
                    config
                        .config_error(format!(
                            "cursor_start value '{text}' uses digits outside ASCII"
                        ))
                        .with_help(model_header_help(
                            "write cursor_start with ASCII digits 0-9",
                            "cursor_start '0'",
                        )),
                )),
                DecimalText::Special | DecimalText::Invalid => Err(config.error(format!(
                    "cursor_start value '{text}' is not a valid integer"
                ))),
            }
        }
        _ => Err(config.error("cursor_start for cursor_type=integer must be a string or integer")),
    }
}

/// Return the `_cursor_contract_key` of a bound that passed its checks.
pub(crate) fn bound_key<N: AuthoredNode>(
    config: &ConfigView<'_, N>,
    value: &N,
    cursor_type: &str,
) -> Option<BoundKey> {
    if cursor_type == INTEGER_CURSOR {
        if let Some(number) = value.integer() {
            return Some(BoundKey::Integer(FiniteDecimal::integer(number)));
        }
        return match decimal_text(config.python, &value.text()?) {
            DecimalText::Finite(decimal) => Some(BoundKey::Integer(decimal)),
            _ => None,
        };
    }
    let text: String = if value.is_date_like() {
        value.python_str()
    } else {
        value.text()?
    };
    match datetime_fromisoformat(&text, config.python.minor_version()) {
        Ok(parsed) => Some(timestamp_key(&parsed)),
        Err(IsoError::InvalidString | IsoError::Message(_)) => None,
    }
}

/// Return whether `start < end` as Python compares the two `Decimal` keys.
pub(crate) fn keys_ordered(start: &BoundKey, end: &BoundKey) -> bool {
    match (start, end) {
        (BoundKey::Integer(start), BoundKey::Integer(end)) => start.compare(end) == Ordering::Less,
        (BoundKey::Timestamp(start), BoundKey::Timestamp(end)) => start < end,
        _ => true,
    }
}

/// The UTC float timestamp Python compares, or the overflow of its shift to UTC.
fn timestamp_key(parsed: &IsoDateTime) -> BoundKey {
    let utc_micros: i64 = local_micros(parsed) - parsed.offset_micros.unwrap_or(0);
    let (first, end) = supported_micros();
    if utc_micros < first || utc_micros >= end {
        return BoundKey::Overflow(utc_isoformat(parsed));
    }
    let since_epoch: i64 = utc_micros - epoch_micros();
    let sign: &str = if since_epoch < 0 { "-" } else { "" };
    let magnitude: u64 = since_epoch.unsigned_abs();
    let seconds: u64 = magnitude / MICROS_PER_SECOND.unsigned_abs();
    let micros: u64 = magnitude % MICROS_PER_SECOND.unsigned_abs();
    BoundKey::Timestamp(
        format!("{sign}{seconds}.{micros:06}")
            .parse::<f64>()
            .unwrap_or(f64::NAN),
    )
}
