//! `normalize_timestamp_text`: warehouse timestamp text in an ISO-compatible spelling.

use sqlbuild_core::text::main::is_decimal_digit::is_decimal_digit;
use sqlbuild_core::text::main::python_isspace::python_isspace;
use sqlbuild_core::text::main::python_strip::python_strip;

use crate::algebra::constants::{
    COMPACT_OFFSET_LENGTH, OFFSET_SEPARATOR, SEPARATED_OFFSET_LENGTH, SEPARATOR_POSITION,
    UTC_DESIGNATOR,
};

/// Whether `tail` is a `[+-]dd:?dd` offset with Unicode decimal digits.
fn is_offset(tail: &[char]) -> bool {
    let Some((sign, rest)) = tail.split_first() else {
        return false;
    };
    let digits: Vec<char> = match rest.len() + 1 {
        COMPACT_OFFSET_LENGTH => rest.to_vec(),
        SEPARATED_OFFSET_LENGTH if rest[SEPARATOR_POSITION - 1] == OFFSET_SEPARATOR => rest
            .iter()
            .enumerate()
            .filter(|(index, _)| *index != SEPARATOR_POSITION - 1)
            .map(|(_, character)| *character)
            .collect(),
        _ => return false,
    };
    matches!(sign, '+' | '-') && digits.into_iter().all(is_decimal_digit)
}

/// The length of the UTC designator or offset ending `characters`, if one does.
fn zone_suffix_length(characters: &[char]) -> Option<usize> {
    if characters.last() == Some(&UTC_DESIGNATOR) {
        return Some(1);
    }
    [COMPACT_OFFSET_LENGTH, SEPARATED_OFFSET_LENGTH]
        .into_iter()
        .find(|length| {
            characters.len() >= *length && is_offset(&characters[characters.len() - length..])
        })
}

/// `re.sub(r"\s+(?=(?:Z|[+-]\d{2}:?\d{2})$)", "", value.strip())`.
#[must_use]
pub fn normalize_timestamp_text(value: &str) -> String {
    let characters: Vec<char> = python_strip(value).chars().collect();
    let Some(suffix) = zone_suffix_length(&characters) else {
        return characters.into_iter().collect();
    };
    let zone_start: usize = characters.len() - suffix;
    let mut space_start: usize = zone_start;
    while space_start > 0 && python_isspace(characters[space_start - 1]) {
        space_start -= 1;
    }
    characters[..space_start]
        .iter()
        .chain(&characters[zone_start..])
        .collect()
}
