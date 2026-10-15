//! Fit a readable logical name after a fixed prefix.

use crate::identifier_fitting::_helpers::bytes::{short_hash, truncate_bytes};
use crate::identifier_fitting::constants::SHORTENED_NAME_HASH_LENGTH;

/// The logical name, or its truncation with a hash suffix; `Err` carries the input error message.
pub fn fit_artifact_logical_name(
    (logical_name, fixed_prefix): (&str, &str),
    identifier_limit: i64,
    artifact_label: &str,
) -> Result<String, String> {
    let max_logical_length: i64 = identifier_limit - byte_length(fixed_prefix);
    if max_logical_length < 1 {
        return Err(format!(
            "{artifact_label} prefix '{fixed_prefix}' does not fit within identifier limit {identifier_limit}"
        ));
    }
    if byte_length(logical_name) <= max_logical_length {
        return Ok(logical_name.to_owned());
    }
    let suffix_length: i64 = byte_length_of(SHORTENED_NAME_HASH_LENGTH) + 1;
    if max_logical_length <= suffix_length {
        return Err(format!(
            "{artifact_label} name for '{logical_name}' cannot fit within identifier limit {identifier_limit}"
        ));
    }
    let kept: usize = usize::try_from(max_logical_length - suffix_length).unwrap_or(0);
    Ok(format!(
        "{}_{}",
        truncate_bytes(logical_name, kept),
        short_hash(logical_name)
    ))
}

fn byte_length(value: &str) -> i64 {
    byte_length_of(value.len())
}

fn byte_length_of(length: usize) -> i64 {
    i64::try_from(length).unwrap_or(i64::MAX)
}
