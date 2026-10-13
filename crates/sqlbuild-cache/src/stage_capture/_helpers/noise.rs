//! The three noise patterns of a capture, matched as Python's `re` matches them.

use sqlbuild_core::text::main::is_decimal_digit::is_decimal_digit;
use sqlbuild_core::text::main::python_isalnum::python_isalnum;

use crate::stage_capture::constants::{
    ENGINE_NAMESPACE_PREFIX, INVOCATION_ID_MASK, INVOCATION_ID_PARTS, REFACTOR_STAGING_MASK,
    REFACTOR_STAGING_PREFIX,
};

/// Python's `\w` for a `str` pattern.
fn is_word(character: char) -> bool {
    character == '_' || python_isalnum(character)
}

/// Python's `\b` between `characters[at - 1]` and `characters[at]`.
fn at_boundary(characters: &[char], at: usize) -> bool {
    let before: bool = at > 0 && is_word(characters[at - 1]);
    let after: bool = characters
        .get(at)
        .is_some_and(|character| is_word(*character));
    before != after
}

/// Whether `characters[at..]` starts with `literal`.
fn starts_with(characters: &[char], at: usize, literal: &str) -> bool {
    (at..)
        .zip(literal.chars())
        .all(|(position, expected)| characters.get(position) == Some(&expected))
}

/// The number of characters from `at` that satisfy `accepts`, at most `limit`.
fn run_length(characters: &[char], at: usize, limit: usize, accepts: fn(char) -> bool) -> usize {
    characters[at.min(characters.len())..]
        .iter()
        .take(limit)
        .take_while(|character| accepts(**character))
        .count()
}

/// Whether `character` is a lowercase hexadecimal digit, `[0-9a-f]`.
fn is_lower_hex(character: char) -> bool {
    character.is_ascii_digit() || ('a'..='f').contains(&character)
}

/// Whether `character` is in `[0-9a-z_]`.
fn is_staging_char(character: char) -> bool {
    character.is_ascii_digit() || character.is_ascii_lowercase() || character == '_'
}

/// The end of `\b\d{8}T\d{6}Z_[0-9a-f]{12}\b` matched at `at`.
fn invocation_id_end(characters: &[char], at: usize) -> Option<usize> {
    let (date, time, hex) = INVOCATION_ID_PARTS;
    if !at_boundary(characters, at) || run_length(characters, at, date, is_decimal_digit) != date {
        return None;
    }
    let mut position: usize = at + date;
    if characters.get(position) != Some(&'T') {
        return None;
    }
    position += 1;
    if run_length(characters, position, time, is_decimal_digit) != time {
        return None;
    }
    position += time;
    if !starts_with(characters, position, "Z_") {
        return None;
    }
    position += 2;
    if run_length(characters, position, hex, is_lower_hex) != hex {
        return None;
    }
    position += hex;
    at_boundary(characters, position).then_some(position)
}

/// The end of `-native-v\d+\b` matched at `at`.
fn engine_namespace_end(characters: &[char], at: usize) -> Option<usize> {
    if !starts_with(characters, at, ENGINE_NAMESPACE_PREFIX) {
        return None;
    }
    let start: usize = at + ENGINE_NAMESPACE_PREFIX.chars().count();
    let digits: usize = run_length(characters, start, usize::MAX, is_decimal_digit);
    (digits > 0 && at_boundary(characters, start + digits)).then_some(start + digits)
}

/// The end of `\bsqb-refactor-[0-9a-z_]+` matched at `at`.
fn refactor_staging_end(characters: &[char], at: usize) -> Option<usize> {
    if !at_boundary(characters, at) || !starts_with(characters, at, REFACTOR_STAGING_PREFIX) {
        return None;
    }
    let start: usize = at + REFACTOR_STAGING_PREFIX.chars().count();
    let length: usize = run_length(characters, start, usize::MAX, is_staging_char);
    (length > 0).then_some(start + length)
}

/// `pattern.sub(replacement, text)` for a pattern that never matches the empty string.
fn substituted(
    text: &str,
    matched_end: fn(&[char], usize) -> Option<usize>,
    replacement: &str,
) -> String {
    let characters: Vec<char> = text.chars().collect();
    let mut result: String = String::with_capacity(text.len());
    let mut position: usize = 0;
    while position < characters.len() {
        match matched_end(&characters, position) {
            Some(end) => {
                result.push_str(replacement);
                position = end;
            }
            None => {
                result.push(characters[position]);
                position += 1;
            }
        }
    }
    result
}

/// Mask invocation ids, then native store suffixes, then refactor staging folders.
pub(crate) fn masked(text: &str) -> String {
    let without_ids: String = substituted(text, invocation_id_end, INVOCATION_ID_MASK);
    let without_namespaces: String = substituted(&without_ids, engine_namespace_end, "");
    substituted(
        &without_namespaces,
        refactor_staging_end,
        REFACTOR_STAGING_MASK,
    )
}
