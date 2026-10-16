//! `sql_digest`: the logged digest of one SQL statement.

use sha2::{Digest, Sha256};

use crate::diagnostic_routing::constants::SQL_DIGEST_PREFIX;

/// `sha256:` followed by the hex SHA-256 of the statement's UTF-8 bytes.
#[must_use]
pub fn sql_digest(sql: &str) -> String {
    format!("{SQL_DIGEST_PREFIX}{:x}", Sha256::digest(sql.as_bytes()))
}
