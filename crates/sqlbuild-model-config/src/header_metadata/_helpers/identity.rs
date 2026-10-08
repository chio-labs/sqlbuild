//! `validate_resource_identity` for ASCII names, with its suggested snake_case spelling.

use crate::errors::{ConfigError, ErrorClass};
use crate::header_metadata::_helpers::text::ascii_strip;
use crate::header_metadata::constants::{FALLBACK_IDENTITY, IDENTITY_HELP};
use crate::header_metadata::models::HeaderMetadataStop;

/// Raise `ResourceIdentityError` unless `name` is canonical snake_case; defer non-ASCII names.
pub(crate) fn check_identity(name: &str, kind: &str, path: &str) -> Result<(), HeaderMetadataStop> {
    if is_snake_case(name) {
        return Ok(());
    }
    if !name.is_ascii() {
        return Err(HeaderMetadataStop::Unsupported);
    }
    let suggestion = suggested_identity(name);
    Err(HeaderMetadataStop::Error(
        ConfigError::compile(format!(
            "Invalid {kind} identity '{name}' in {path}; use snake_case '{suggestion}'"
        ))
        .with_class(ErrorClass::ResourceIdentity)
        .with_help(IDENTITY_HELP),
    ))
}

/// Return whether `name` fully matches `^[a-z](?:[a-z0-9_]*[a-z0-9])?$`.
fn is_snake_case(name: &str) -> bool {
    let bytes = name.as_bytes();
    match (bytes.first(), bytes.last()) {
        (Some(first), Some(last)) => {
            first.is_ascii_lowercase()
                && (last.is_ascii_lowercase() || last.is_ascii_digit())
                && bytes
                    .iter()
                    .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || *byte == b'_')
        }
        _ => false,
    }
}

/// Return `suggest_resource_identity` for an ASCII public identity.
fn suggested_identity(name: &str) -> String {
    let characters: Vec<char> = ascii_strip(name).chars().collect();
    let acronyms = split_where(&characters, |index| {
        characters[index - 1].is_ascii_uppercase()
            && characters[index].is_ascii_uppercase()
            && characters
                .get(index + 1)
                .is_some_and(char::is_ascii_lowercase)
    });
    let words = split_where(&acronyms, |index| {
        (acronyms[index - 1].is_ascii_lowercase() || acronyms[index - 1].is_ascii_digit())
            && acronyms[index].is_ascii_uppercase()
    });
    let mut replaced = String::with_capacity(words.len());
    let mut in_invalid_run = false;
    for character in words {
        if character.is_ascii_alphanumeric() || character == '_' {
            replaced.push(character.to_ascii_lowercase());
            in_invalid_run = false;
        } else if !in_invalid_run {
            replaced.push('_');
            in_invalid_run = true;
        }
    }
    let corrected = replaced.trim_matches('_');
    if corrected.is_empty() {
        FALLBACK_IDENTITY.to_owned()
    } else {
        corrected.to_owned()
    }
}

/// Insert `_` before every index after the first where `boundary` holds.
fn split_where(characters: &[char], boundary: impl Fn(usize) -> bool) -> Vec<char> {
    let mut result: Vec<char> = Vec::with_capacity(characters.len() * 2);
    for (index, character) in characters.iter().enumerate() {
        if index > 0 && boundary(index) {
            result.push('_');
        }
        result.push(*character);
    }
    result
}
