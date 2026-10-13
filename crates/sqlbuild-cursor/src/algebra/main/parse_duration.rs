//! `parse_duration`: the units of a duration string like `1y6mo`, `30d` or `6h`.

use sqlbuild_core::text::main::decimal_digit_value::decimal_digit_value;

use crate::algebra::constants::{LINE_FEED, UNIT_SUFFIXES};
use crate::algebra::models::DurationDigits;

/// The ASCII digits of one `(\d+)<suffix>` group at the start of `characters`, and its length.
fn unit_group(characters: &[char], suffix: &str) -> Option<(String, usize)> {
    let digits: String = characters
        .iter()
        .map_while(|character| decimal_digit_value(*character))
        .map(|digit| char::from(b'0' + digit as u8))
        .collect();
    let count: usize = digits.chars().count();
    let suffix_characters: Vec<char> = suffix.chars().collect();
    let matched: bool = count > 0 && characters[count..].starts_with(&suffix_characters);
    matched.then(|| (digits, count + suffix_characters.len()))
}

fn is_zero(digits: &str) -> bool {
    digits.bytes().all(|byte| byte == b'0')
}

/// Each unit's digits, `"0"` when absent, if `value` fully matches and is not zero.
#[must_use]
pub fn parse_duration(value: &str) -> Option<DurationDigits> {
    let characters: Vec<char> = value.chars().collect();
    let mut position: usize = 0;
    let mut groups: Vec<String> = Vec::with_capacity(UNIT_SUFFIXES.len());
    for suffix in UNIT_SUFFIXES {
        match unit_group(&characters[position..], suffix) {
            Some((digits, length)) => {
                groups.push(digits);
                position += length;
            }
            None => groups.push(String::from("0")),
        }
    }
    let rest: &[char] = &characters[position..];
    if !(rest.is_empty() || rest == [LINE_FEED]) {
        return None;
    }
    if groups.iter().all(|digits| is_zero(digits)) {
        return None;
    }
    let mut parts = groups.into_iter();
    let mut next = || parts.next().unwrap_or_default();
    Some(DurationDigits {
        years: next(),
        months: next(),
        days: next(),
        hours: next(),
        minutes: next(),
        seconds: next(),
    })
}
