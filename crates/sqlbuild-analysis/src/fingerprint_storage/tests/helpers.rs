use crate::fingerprint_storage::models::StoredFingerprint;

/// A model fingerprint row with `definition` and fixed other fields.
pub(crate) fn stored_fingerprint(definition: String) -> StoredFingerprint {
    StoredFingerprint {
        node_type: "model".to_owned(),
        node_name: "o'rders".to_owned(),
        target_database: None,
        target_schema: Some("main".to_owned()),
        target_name: Some("orders".to_owned()),
        run_id: "run".to_owned(),
        definition_hash: "d".to_owned(),
        version_hash: String::new(),
        schema_fingerprint: "s".to_owned(),
        definition,
        metadata_json: "{}".to_owned(),
        ts: "2026-01-01T00:00:00".to_owned(),
    }
}
