//! Bare MODEL header words read as booleans, null, integers or floats.

use crate::compiler::models::HeaderWord;
use sqlbuild_core::text::main::decimal_digit_value::decimal_digit_value;

pub(crate) const TRUE_WORD: &str = "true";
pub(crate) const FALSE_WORD: &str = "false";
pub(crate) const NULL_WORD: &str = "null";
const DECIMAL_POINT: char = '.';
const NEGATIVE_SIGN: &str = "-";
const ZERO_DIGITS: &str = "0";

/// The ASCII form of a run of Python decimal digits, or `None` if any character is not one.
fn ascii_digits(text: &str) -> Option<String> {
    text.chars()
        .map(|character| {
            decimal_digit_value(character).and_then(|value| char::from_digit(value, 10))
        })
        .collect()
}

pub(crate) fn signed(word: &str) -> (&str, &str) {
    match word.strip_prefix(['+', '-']) {
        Some(rest) => (&word[..1], rest),
        None => ("", word),
    }
}

pub(crate) fn integer(sign: &str, body: &str) -> Option<HeaderWord> {
    let digits = ascii_digits(body).filter(|digits| !digits.is_empty())?;
    let trimmed = digits.trim_start_matches('0');
    let magnitude = if trimmed.is_empty() { "0" } else { trimmed };
    let negative = sign == NEGATIVE_SIGN && magnitude != ZERO_DIGITS;
    Some(HeaderWord::Integer(if negative {
        format!("-{magnitude}")
    } else {
        magnitude.to_owned()
    }))
}

pub(crate) fn float(sign: &str, body: &str) -> Option<HeaderWord> {
    let (whole, fraction) = body.split_once(DECIMAL_POINT)?;
    let whole = ascii_digits(whole)?;
    let fraction = ascii_digits(fraction)?;
    if whole.is_empty() && fraction.is_empty() {
        return None;
    }
    Some(
        format!("{sign}{whole}.{fraction}0")
            .parse::<f64>()
            .map_or(HeaderWord::Text, HeaderWord::Float),
    )
}
