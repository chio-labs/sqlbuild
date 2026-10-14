//! Persisted rename identity of a model.

use crate::planner_migrations::_helpers::proofs::encoding::encode;
use crate::planner_migrations::_helpers::proofs::fingerprint::{identity_metadata, normalized};
use serde_json::json;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;

/// Hash normalized SQL and metadata exactly as migration-fingerprint-v1.
pub fn migration_fingerprint(
    sql: &str,
    metadata: &str,
    identities: &BTreeMap<String, String>,
    dialect: &str,
) -> Result<Option<String>, String> {
    let Some(sql) = normalized(sql, identities, dialect)? else {
        return Ok(None);
    };
    let payload =
        encode(&json!({"metadata": identity_metadata(metadata, identities), "sql": sql}))?;
    Ok(Some(format!("{:x}", Sha256::digest(payload.as_bytes()))))
}
