//! Shortest round-trip float text in Python's and orjson's layouts.

use crate::json::constants::{
    ORJSON_EXPONENT_DIGITS, ORJSON_FIXED_EXPONENTS, PYTHON_EXPONENT_DIGITS, PYTHON_FIXED_EXPONENTS,
};
use std::ops::RangeInclusive;

fn scientific_parts(text: &str) -> (String, i32) {
    let (mantissa, exponent) = text.split_once('e').unwrap_or((text, "0"));
    let digits: String = mantissa.chars().filter(char::is_ascii_digit).collect();
    let (sign, magnitude) = exponent
        .strip_prefix('-')
        .map_or((1, exponent), |magnitude| (-1, magnitude));
    let exponent = magnitude
        .bytes()
        .fold(0_i32, |total, digit| total * 10 + i32::from(digit - b'0'));
    (digits, sign * exponent)
}

/// Shortest round-trip digits of `|value|`, ties rounded half to even as CPython does.
fn shortest_digits(value: f64) -> (String, i32) {
    let (shortest, _) = scientific_parts(&format!("{:e}", value.abs()));
    let precision = shortest.len().saturating_sub(1);
    scientific_parts(&format!("{:.precision$e}", value.abs()))
}

/// Fixed-point layout of `digits` with the decimal point after `point` digits.
fn fixed(digits: &str, point: i32) -> String {
    match usize::try_from(point) {
        Err(_) | Ok(0) => format!("0.{}{digits}", "0".repeat(point.unsigned_abs() as usize)),
        Ok(point) if point >= digits.len() => {
            format!("{digits}{}.0", "0".repeat(point - digits.len()))
        }
        Ok(point) => format!("{}.{}", &digits[..point], &digits[point..]),
    }
}

fn scientific(digits: &str, exponent: i32, exponent_digits: usize) -> String {
    let (first, rest) = digits.split_at(1);
    let mantissa = if rest.is_empty() {
        first.to_owned()
    } else {
        format!("{first}.{rest}")
    };
    let sign = if exponent.is_negative() { '-' } else { '+' };
    let magnitude = exponent.unsigned_abs();
    format!("{mantissa}e{sign}{magnitude:0exponent_digits$}")
}

fn layout(value: f64, fixed_exponents: RangeInclusive<i32>, exponent_digits: usize) -> String {
    let (digits, exponent) = shortest_digits(value);
    let body = if fixed_exponents.contains(&exponent) {
        fixed(&digits, exponent + 1)
    } else {
        scientific(&digits, exponent, exponent_digits)
    };
    let sign = if value.is_sign_negative() { "-" } else { "" };
    format!("{sign}{body}")
}

/// Python's `repr(float)`, including `nan`, `inf` and `-inf`.
pub(crate) fn python_repr(value: f64) -> String {
    match value {
        _ if value.is_nan() => "nan".to_owned(),
        _ if value.is_infinite() && value.is_sign_positive() => "inf".to_owned(),
        _ if value.is_infinite() => "-inf".to_owned(),
        _ => layout(value, PYTHON_FIXED_EXPONENTS, PYTHON_EXPONENT_DIGITS),
    }
}

/// orjson's text for a finite float.
pub(crate) fn orjson_text(value: f64) -> String {
    layout(value, ORJSON_FIXED_EXPONENTS, ORJSON_EXPONENT_DIGITS)
}
