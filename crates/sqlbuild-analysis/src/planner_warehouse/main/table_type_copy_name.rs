//! The deterministic conversion copy name of a table-type change.

use crate::planner_warehouse::constants::TABLE_TYPE_COPY_PREFIX;
use sha2::{Digest, Sha256};

/// Prefix, the target name fitted to the identifier limit, and a short digest suffix.
pub fn table_type_copy_name(target_name: &str, identifier_limit: i64) -> String {
    let digest = format!("{:x}", Sha256::digest(target_name.as_bytes()));
    let suffix = format!("__{}", &digest[..12]);
    let reserved = (TABLE_TYPE_COPY_PREFIX.chars().count() + suffix.chars().count()) as i64;
    let available = usize::try_from((identifier_limit - reserved).max(0)).unwrap_or(0);
    let fitted: String = target_name.chars().take(available).collect();
    format!("{TABLE_TYPE_COPY_PREFIX}{fitted}{suffix}")
}
