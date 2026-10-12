//! Integers and floats of the YAML 1.2 core schema.

use crate::errors::{ConfigError, ConfigErrorKind};
use crate::models::ConfigValue;
use crate::yaml::constants::{INFINITY_WORDS, MAX_INTEGER_DIGITS, NAN_WORDS};

fn construct_error(message: String) -> ConfigError {
    ConfigError::new(ConfigErrorKind::Construct, message)
}

/// A decimal, `0o` octal or `0x` hexadecimal integer; decimals beyond 64 bits stay exact.
pub(crate) fn construct_int(text: &str) -> Result<ConfigValue, ConfigError> {
    let radix_digits = text
        .strip_prefix("0o")
        .map(|digits| (8, digits))
        .or_else(|| text.strip_prefix("0x").map(|digits| (16, digits)));
    if let Some((radix, digits)) = radix_digits {
        return i64::from_str_radix(digits, radix)
            .map(ConfigValue::Integer)
            .map_err(|_| construct_error(format!("integer {text} is out of range")));
    }
    if let Ok(value) = text.parse::<i64>() {
        return Ok(ConfigValue::Integer(value));
    }
    let negative = text.starts_with('-');
    let unsigned = text.strip_prefix(['+', '-']).unwrap_or(text);
    if unsigned.is_empty() || !unsigned.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err(construct_error(format!("{text:?} is not an integer")));
    }
    let digits = unsigned.trim_start_matches('0');
    if digits.len() > MAX_INTEGER_DIGITS {
        return Err(ConfigError::new(
            ConfigErrorKind::Unsupported,
            "integers longer than 4300 digits",
        ));
    }
    Ok(ConfigValue::BigInteger(format!(
        "{}{digits}",
        if negative { "-" } else { "" }
    )))
}

/// A decimal float, `.inf` with an optional sign, or `.nan`.
pub(crate) fn construct_float(text: &str) -> Result<ConfigValue, ConfigError> {
    let (negative, number) = match text.as_bytes().first() {
        Some(b'-') => (true, &text[1..]),
        Some(b'+') => (false, &text[1..]),
        _ => (false, text),
    };
    let magnitude = if INFINITY_WORDS.contains(&number) {
        f64::INFINITY
    } else if NAN_WORDS.contains(&text) {
        return Ok(ConfigValue::Float(f64::NAN));
    } else {
        number
            .parse::<f64>()
            .map_err(|_| construct_error(format!("{text:?} is not a float")))?
    };
    Ok(ConfigValue::Float(if negative {
        -magnitude
    } else {
        magnitude
    }))
}
