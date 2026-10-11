//! Python's `compute_function_definition_hash`.

use sha2::{Digest, Sha256};

use crate::sql_tokens::constants::SQL_FUNCTION_LANGUAGE;
use crate::sql_tokens::main::compiler_query_fingerprint::compiler_query_fingerprint;

/// SQL definitions fingerprinted like queries; other languages by the SHA-256 of their text.
pub fn definition_fingerprint(
    sql: &str,
    language: &str,
    dialect: Option<&str>,
) -> Result<String, String> {
    if language == SQL_FUNCTION_LANGUAGE {
        return compiler_query_fingerprint(sql, dialect);
    }
    Ok(format!("{:x}", Sha256::digest(sql.as_bytes())))
}
