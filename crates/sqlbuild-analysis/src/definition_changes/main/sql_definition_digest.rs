//! The digest of SQL with whitespace, comments and keyword case ignored.

use crate::definition_changes::main::definition_digest::definition_digest;
use crate::sql_tokens::main::compiler_query_fingerprint::compiler_query_fingerprint;

/// The generic-tokenizer fingerprint of `sql`, or the digest of its text when it cannot tokenize.
pub fn sql_definition_digest(sql: &str) -> String {
    match compiler_query_fingerprint(sql, None) {
        Ok(fingerprint) => fingerprint,
        Err(_) => definition_digest(&[sql]),
    }
}
