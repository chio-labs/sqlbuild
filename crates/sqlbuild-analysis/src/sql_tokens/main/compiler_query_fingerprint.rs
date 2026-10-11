//! Python's `compute_query_hash`: a query fingerprint under the project's dialect alias.

use crate::sql_tokens::constants::{FINGERPRINT_DIALECT_ALIASES, GENERIC_FINGERPRINT_DIALECT};
use crate::sql_tokens::main::query_fingerprint::query_fingerprint;

/// The fingerprint of `sql` under `dialect` (aliased, or generic when empty or absent).
pub fn compiler_query_fingerprint(sql: &str, dialect: Option<&str>) -> Result<String, String> {
    let dialect = match dialect.filter(|name| !name.is_empty()) {
        None => GENERIC_FINGERPRINT_DIALECT,
        Some(name) => FINGERPRINT_DIALECT_ALIASES
            .iter()
            .find(|(alias, _)| *alias == name)
            .map_or(name, |(_, target)| target),
    };
    query_fingerprint(sql, dialect)
}
