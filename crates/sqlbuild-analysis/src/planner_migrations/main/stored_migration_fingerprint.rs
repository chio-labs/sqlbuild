//! Read persisted migration hashes without changing their representation.

/// Read only string migration fingerprints from object metadata.
pub fn stored_migration_fingerprint(metadata: &str) -> Option<String> {
    let payload: serde_json::Value = match serde_json::from_str(metadata) {
        Ok(payload) => payload,
        Err(_) => return None,
    };
    payload
        .get("migration_fingerprint")?
        .as_str()
        .map(str::to_owned)
}
