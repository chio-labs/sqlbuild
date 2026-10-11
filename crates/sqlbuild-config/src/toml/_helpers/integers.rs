//! Values the TOML parser rejects but `tomllib` reads: integers beyond 64 bits and deep nesting.

use crate::errors::{ConfigError, ConfigErrorKind};
use crate::models::{ConfigValue, Natural};

const DECIMAL_RADIX: u32 = 10;
/// Noncharacters that can mark a placeholder; the first absent from a document is used.
const PLACEHOLDER_MARKS: std::ops::RangeInclusive<u32> = 0xFDD0..=0xFDEF;

/// A value read apart from the document: its byte range there and the value it stands for.
pub(crate) type Placeholder = (usize, usize, ConfigValue);

fn digits_with_separators(body: &str, radix: u32) -> Option<Vec<u32>> {
    let mut values: Vec<u32> = Vec::new();
    let mut after_digit = false;
    for character in body.chars() {
        if character == '_' && after_digit {
            after_digit = false;
            continue;
        }
        values.push(character.to_digit(radix)?);
        after_digit = true;
    }
    after_digit.then_some(values)
}

fn natural(values: &[u32], radix: u32) -> String {
    values
        .iter()
        .fold(Natural::default(), |total, value| {
            total.times_plus(radix, *value)
        })
        .decimal()
}

/// The signed decimal digits of a TOML integer literal outside the 64-bit range, if `raw` is one.
pub(crate) fn large_integer(raw: &str) -> Option<String> {
    let (radix, body, negative) = match raw.get(..2) {
        Some("0x") => (16, &raw[2..], false),
        Some("0o") => (8, &raw[2..], false),
        Some("0b") => (2, &raw[2..], false),
        _ => match raw.strip_prefix('-') {
            Some(rest) => (10, rest, true),
            None => (10, raw.strip_prefix('+').unwrap_or(raw), false),
        },
    };
    let values = digits_with_separators(body, radix)?;
    if radix == DECIMAL_RADIX && values.len() > 1 && values[0] == 0 {
        return None;
    }
    let digits = natural(&values, radix);
    let signed = if negative {
        format!("-{digits}")
    } else {
        digits
    };
    signed.parse::<i64>().is_err().then_some(signed)
}

/// A placeholder mark that neither appears in `text` nor can come from one of its escapes.
pub(crate) fn placeholder_mark(text: &str) -> Result<char, ConfigError> {
    let lowered = text.to_ascii_lowercase();
    PLACEHOLDER_MARKS
        .filter_map(char::from_u32)
        .find(|mark| !text.contains(*mark) && !lowered.contains(&format!("{:x}", u32::from(*mark))))
        .ok_or_else(|| {
            ConfigError::new(
                ConfigErrorKind::Unsupported,
                "large integers in text using every placeholder mark are not read natively",
            )
        })
}

/// `text` with each placeholder range replaced by a string marked by `mark`.
pub(crate) fn substitute_placeholders(text: &str, integers: &[Placeholder], mark: char) -> String {
    let mut substituted = String::with_capacity(text.len());
    let mut copied = 0;
    for (index, (start, end, _)) in integers.iter().enumerate() {
        substituted.push_str(&text[copied..*start]);
        substituted.push_str(&format!("\"{mark}{index}\""));
        copied = *end;
    }
    substituted.push_str(&text[copied..]);
    substituted
}

/// `value` with each placeholder string turned back into the value it stands for.
pub(crate) fn restore_placeholders(
    value: ConfigValue,
    integers: &[Placeholder],
    mark: char,
) -> ConfigValue {
    match value {
        ConfigValue::String(text) => match text
            .strip_prefix(mark)
            .and_then(|index| {
                integers
                    .iter()
                    .enumerate()
                    .find(|(position, _)| position.to_string() == index)
            })
            .map(|(_, integer)| integer)
        {
            Some((_, _, restored)) => restored.clone(),
            None => ConfigValue::String(text),
        },
        ConfigValue::List(items) => ConfigValue::List(
            items
                .into_iter()
                .map(|item| restore_placeholders(item, integers, mark))
                .collect(),
        ),
        ConfigValue::Map(entries) => ConfigValue::Map(
            entries
                .into_iter()
                .map(|(key, item)| (key, restore_placeholders(item, integers, mark)))
                .collect(),
        ),
        other => other,
    }
}
