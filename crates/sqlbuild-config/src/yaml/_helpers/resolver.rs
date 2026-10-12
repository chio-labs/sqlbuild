//! YAML 1.2 core schema tags for plain scalars, plus merge keys.

use crate::yaml::constants::{
    BOOL_TAG, BOOL_WORDS, FLOAT_TAG, INFINITY_WORDS, INT_TAG, MERGE_KEY, MERGE_TAG, NAN_WORDS,
    NULL_TAG, NULL_WORDS, STR_TAG,
};

/// The text without one leading `+` or `-`.
fn unsigned(text: &str) -> &str {
    text.strip_prefix(['+', '-']).unwrap_or(text)
}

fn is_digits(text: &str, radix: u32) -> bool {
    !text.is_empty() && text.chars().all(|character| character.is_digit(radix))
}

/// `[-+]?[0-9]+`, `0o[0-7]+` or `0x[0-9a-fA-F]+`.
pub(crate) fn is_int(text: &str) -> bool {
    is_digits(unsigned(text), 10)
        || text
            .strip_prefix("0o")
            .is_some_and(|digits| is_digits(digits, 8))
        || text
            .strip_prefix("0x")
            .is_some_and(|digits| is_digits(digits, 16))
}

/// `[-+]?(\.[0-9]+|[0-9]+(\.[0-9]*)?)([eE][-+]?[0-9]+)?`, `[-+]?.inf` or `.nan`.
fn is_float(text: &str) -> bool {
    let number = unsigned(text);
    if INFINITY_WORDS.contains(&number) || NAN_WORDS.contains(&text) {
        return true;
    }
    let (mantissa, exponent) = number
        .split_once(['e', 'E'])
        .map_or((number, None), |(mantissa, exponent)| {
            (mantissa, Some(exponent))
        });
    let mantissa_valid = match mantissa.split_once('.') {
        Some((whole, fraction)) => {
            (whole.is_empty() && is_digits(fraction, 10))
                || (is_digits(whole, 10) && (fraction.is_empty() || is_digits(fraction, 10)))
        }
        None => is_digits(mantissa, 10),
    };
    mantissa_valid && exponent.is_none_or(|exponent| is_digits(unsigned(exponent), 10))
}

/// The tag of a scalar; `implicit` is true for plain scalars, which the core schema resolves.
pub(crate) fn resolve_scalar(value: &str, implicit: bool) -> &'static str {
    if !implicit {
        STR_TAG
    } else if NULL_WORDS.contains(&value) {
        NULL_TAG
    } else if BOOL_WORDS.iter().any(|(word, _)| *word == value) {
        BOOL_TAG
    } else if is_int(value) {
        INT_TAG
    } else if is_float(value) {
        FLOAT_TAG
    } else if value == MERGE_KEY {
        MERGE_TAG
    } else {
        STR_TAG
    }
}
