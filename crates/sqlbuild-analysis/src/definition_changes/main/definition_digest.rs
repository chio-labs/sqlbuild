//! Digests of definition parts and of normalised SQL.

use sha2::{Digest, Sha256};

use crate::sql_tokens::main::compiler_query_fingerprint::compiler_query_fingerprint;

/// The SHA-256 hex digest of `parts`, each length-prefixed so boundaries cannot shift.
pub fn definition_digest(parts: &[&str]) -> String {
    let mut digest = Sha256::new();
    for part in parts {
        digest.update(part.len().to_string().as_bytes());
        digest.update(b":");
        digest.update(part.as_bytes());
    }
    format!("{:x}", digest.finalize())
}

/// The fingerprint of `sql` with whitespace, comments and keyword case ignored.
///
/// The generic tokenizer is used whatever the adapter, so one snapshot compares across adapters;
/// SQL it cannot tokenize is fingerprinted by its exact text.
pub fn sql_definition_digest(sql: &str) -> String {
    compiler_query_fingerprint(sql, None).unwrap_or_else(|_| definition_digest(&[sql]))
}
