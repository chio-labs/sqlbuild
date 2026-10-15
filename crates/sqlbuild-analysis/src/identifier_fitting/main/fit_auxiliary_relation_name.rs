//! Append a suffix to a relation name within an identifier limit.

use crate::identifier_fitting::_helpers::bytes::{short_hash, truncate_bytes};

/// `base_name + suffix`, shortening the base with a stable hash when too long; `Err` carries the message.
pub fn fit_auxiliary_relation_name(
    base_name: &str,
    suffix: &str,
    identifier_limit: i64,
) -> Result<String, String> {
    let whole: i64 = length(base_name) + length(suffix);
    if whole <= identifier_limit {
        return Ok(format!("{base_name}{suffix}"));
    }
    let hash_part: String = format!("_{}", short_hash(base_name));
    let kept_length: i64 = identifier_limit - length(suffix) - length(&hash_part);
    if kept_length < 1 {
        return Err(format!(
            "auxiliary relation suffix '{suffix}' for '{base_name}' cannot fit within identifier limit {identifier_limit}"
        ));
    }
    let kept: usize = usize::try_from(kept_length).unwrap_or(0);
    Ok(format!(
        "{}{hash_part}{suffix}",
        truncate_bytes(base_name, kept)
    ))
}

fn length(value: &str) -> i64 {
    i64::try_from(value.len()).unwrap_or(i64::MAX)
}
