//! Python's `Decimal(text)`, `str(Decimal)` and `Decimal.normalize().as_tuple()`.

use crate::sql_values::constants::{
    DECIMAL_EMAX, DECIMAL_EMIN, DECIMAL_MAX_EXPONENT, DECIMAL_PRECISION, PLAIN_NOTATION_FLOOR,
};
use crate::sql_values::errors::SqlValueFailure;
use crate::sql_values::models::{DecimalNumber, DecimalSpecial};
use sqlbuild_core::text::main::decimal_digit_value::decimal_digit_value;

const ZERO_DIGITS: &str = "0";
const INFINITY_SPELLINGS: [&str; 2] = ["inf", "infinity"];
const NAN_PREFIX: &str = "nan";
const SIGNALING_NAN_PREFIX: &str = "snan";
/// libmpdec's smallest exponent: `MIN_EMIN - (MAX_PREC - 1)`.
const DECIMAL_MIN_EXPONENT: i128 = -1_999_999_999_999_999_997;

/// The text with whitespace stripped, underscores dropped and Unicode digits made ASCII.
fn ascii_text(text: &str) -> Option<String> {
    str::trim(text)
        .chars()
        .filter(|character| *character != '_')
        .map(|character| {
            if character.is_ascii() {
                return Some(character.to_ascii_lowercase());
            }
            decimal_digit_value(character).and_then(|value| char::from_digit(value, 10))
        })
        .collect()
}

fn without_leading_zeros(digits: &str) -> String {
    let trimmed = digits.trim_start_matches('0');
    if trimmed.is_empty() {
        "0".to_owned()
    } else {
        trimmed.to_owned()
    }
}

fn is_digits(text: &str) -> bool {
    !text.is_empty() && text.bytes().all(|byte| byte.is_ascii_digit())
}

fn special(body: &str) -> Option<DecimalSpecial> {
    if INFINITY_SPELLINGS.contains(&body) {
        return Some(DecimalSpecial::Infinity);
    }
    let payload = |rest: &str| {
        (rest.is_empty() || is_digits(rest)).then(|| {
            let digits = without_leading_zeros(rest);
            if digits == ZERO_DIGITS {
                String::new()
            } else {
                digits
            }
        })
    };
    if let Some(rest) = body.strip_prefix(SIGNALING_NAN_PREFIX) {
        return payload(rest).map(DecimalSpecial::SignalingNaN);
    }
    body.strip_prefix(NAN_PREFIX)
        .and_then(payload)
        .map(DecimalSpecial::NaN)
}

fn exponent_value(text: Option<&str>) -> Option<i128> {
    let Some(text) = text else {
        return Some(0);
    };
    let (negative, digits) = match text.as_bytes().first() {
        Some(b'-') => (true, &text[1..]),
        Some(b'+') => (false, &text[1..]),
        _ => (false, text),
    };
    if !is_digits(digits) {
        return None;
    }
    let magnitude = without_leading_zeros(digits);
    let value = magnitude.parse::<i128>().unwrap_or(i128::MAX);
    Some(if negative { -value } else { value })
}

/// `Decimal(text)`, or `None` where Python raises `InvalidOperation`.
pub(crate) fn parse_decimal(text: &str) -> Option<DecimalNumber> {
    let ascii = ascii_text(text)?;
    let (negative, body) = match ascii.as_bytes().first() {
        Some(b'-') => (true, &ascii[1..]),
        Some(b'+') => (false, &ascii[1..]),
        _ => (false, ascii.as_str()),
    };
    if let Some(special) = special(body) {
        return Some(DecimalNumber {
            negative,
            special: Some(special),
            digits: "0".to_owned(),
            exponent: 0,
        });
    }
    let (mantissa, exponent) = match body.split_once('e') {
        Some((mantissa, exponent)) => (mantissa, Some(exponent)),
        None => (body, None),
    };
    let (whole, fraction) = mantissa.split_once('.').unwrap_or((mantissa, ""));
    let digits_ok =
        (whole.is_empty() || is_digits(whole)) && (fraction.is_empty() || is_digits(fraction));
    if !digits_ok || (whole.is_empty() && fraction.is_empty()) {
        return None;
    }
    let exponent = exponent_value(exponent)?.saturating_sub(fraction.len() as i128);
    if exponent > i128::from(DECIMAL_MAX_EXPONENT) || exponent < DECIMAL_MIN_EXPONENT {
        return None;
    }
    Some(DecimalNumber {
        negative,
        special: None,
        digits: without_leading_zeros(&format!("{whole}{fraction}")),
        exponent: exponent as i64,
    })
}

/// `str(Decimal)`: the scientific string of the decimal specification.
pub(crate) fn decimal_text(number: &DecimalNumber) -> String {
    let sign = if number.negative { "-" } else { "" };
    match &number.special {
        Some(DecimalSpecial::Infinity) => return format!("{sign}Infinity"),
        Some(DecimalSpecial::NaN(payload)) => return format!("{sign}NaN{payload}"),
        Some(DecimalSpecial::SignalingNaN(payload)) => return format!("{sign}sNaN{payload}"),
        None => {}
    }
    let digits = &number.digits;
    let length = digits.len() as i64;
    let left_digits = number.exponent + length;
    let dot_place = if number.exponent <= 0 && left_digits > PLAIN_NOTATION_FLOOR {
        left_digits
    } else {
        1
    };
    let (whole, fraction) = if dot_place <= 0 {
        (
            "0".to_owned(),
            format!(".{}{digits}", "0".repeat((-dot_place) as usize)),
        )
    } else if dot_place >= length {
        (
            format!("{digits}{}", "0".repeat((dot_place - length) as usize)),
            String::new(),
        )
    } else {
        let split = dot_place as usize;
        (digits[..split].to_owned(), format!(".{}", &digits[split..]))
    };
    let exponent = if left_digits == dot_place {
        String::new()
    } else {
        format!("E{:+}", left_digits - dot_place)
    };
    format!("{sign}{whole}{fraction}{exponent}")
}

/// `digits` rounded half-even to drop its last `drop` digits, and whether that carried.
fn round_half_even(digits: &str, drop: usize) -> String {
    if drop == 0 {
        return digits.to_owned();
    }
    if drop > digits.len() {
        return "0".to_owned();
    }
    let (kept, dropped) = digits.split_at(digits.len() - drop);
    let first = dropped.as_bytes()[0];
    let rest_nonzero = dropped[1..].bytes().any(|byte| byte != b'0');
    let last_odd = kept
        .as_bytes()
        .last()
        .is_some_and(|byte| (byte - b'0') % 2 == 1);
    let round_up = first > b'5' || (first == b'5' && (rest_nonzero || last_odd));
    let mut values: Vec<u8> = if kept.is_empty() {
        vec![b'0']
    } else {
        kept.bytes().collect()
    };
    if round_up {
        let mut index = values.len();
        loop {
            if index == 0 {
                values.insert(0, b'1');
                break;
            }
            index -= 1;
            if values[index] == b'9' {
                values[index] = b'0';
            } else {
                values[index] += 1;
                break;
            }
        }
    }
    without_leading_zeros(&String::from_utf8(values).unwrap_or_default())
}

/// `Decimal.normalize().as_tuple()` in the default context: sign, digits and exponent.
pub(crate) fn normalized_parts(
    number: &DecimalNumber,
) -> Result<(bool, String, i64), SqlValueFailure> {
    if number.digits == ZERO_DIGITS {
        return Ok((number.negative, "0".to_owned(), 0));
    }
    let mut digits = number.digits.clone();
    let mut exponent = number.exponent;
    if digits.len() > DECIMAL_PRECISION {
        let drop = digits.len() - DECIMAL_PRECISION;
        digits = round_half_even(&digits, drop);
        exponent += drop as i64;
        if digits.len() > DECIMAL_PRECISION {
            digits.pop();
            exponent += 1;
        }
    }
    if exponent + digits.len() as i64 - 1 > DECIMAL_EMAX {
        return Err(SqlValueFailure::DecimalOverflow);
    }
    let tiny = DECIMAL_EMIN - (DECIMAL_PRECISION as i64 - 1);
    if exponent < tiny {
        digits = round_half_even(&digits, (tiny - exponent) as usize);
        exponent = tiny;
        if digits == ZERO_DIGITS {
            return Ok((number.negative, digits, 0));
        }
    }
    let trimmed = digits.trim_end_matches('0');
    exponent += (digits.len() - trimmed.len()) as i64;
    Ok((number.negative, trimmed.to_owned(), exponent))
}
