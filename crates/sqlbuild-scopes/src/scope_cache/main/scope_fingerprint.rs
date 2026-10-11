//! `scope_index_fingerprint`: a hash of the scope-relevant config and authored sources.

use std::path::Path;

use sqlbuild_core::json::models::JsonValue;

use crate::scope_cache::_helpers::fingerprint::{
    SourceRecord, config_bytes, source_record, source_records,
};
use crate::scope_cache::_helpers::json::{canonical_json, integer, object, sha256_hex, text};
use crate::scope_cache::constants::{CACHE_SCHEMA_VERSION, FINGERPRINT_ALGORITHM_VERSION};
use crate::scope_cache::models::{Fingerprint, FingerprintInputs};

/// The fingerprint of `project_dir`, or why Python has none or raises.
#[must_use]
pub fn scope_fingerprint(project_dir: &Path, inputs: &FingerprintInputs) -> Fingerprint {
    let mut records: Vec<SourceRecord> = Vec::new();
    for name in &inputs.config_files {
        let path = project_dir.join(name);
        if !path.is_file() {
            continue;
        }
        let Ok(raw) = std::fs::read(&path) else {
            return Fingerprint::Unavailable;
        };
        let Ok(content) = config_bytes(name, &raw) else {
            return Fingerprint::Unserializable;
        };
        records.push(source_record(name, "config", &content));
    }
    let mut roots: Vec<String> = inputs.roots.clone();
    roots.sort();
    roots.dedup();
    let Some(sources) = source_records(project_dir, &roots, inputs) else {
        return Fingerprint::Unavailable;
    };
    records.extend(sources);
    records.sort_by(|left, right| (&left.0, left.1).cmp(&(&right.0, right.1)));
    let mut sources: Vec<JsonValue> = Vec::with_capacity(records.len());
    for (path, role, digest) in &records {
        sources.push(object(vec![
            ("path", text(path)),
            ("role", text(role)),
            ("sha256", text(digest)),
        ]));
    }
    let payload: JsonValue = object(vec![
        ("algorithm_version", integer(FINGERPRINT_ALGORITHM_VERSION)),
        ("cache_schema_version", integer(CACHE_SCHEMA_VERSION)),
        (
            "ownership_roots",
            JsonValue::Array(roots.iter().map(|root| text(root)).collect()),
        ),
        ("sources", JsonValue::Array(sources)),
        ("sqlbuild_version", text(&inputs.sqlbuild_version)),
    ]);
    match canonical_json(&payload) {
        Ok(encoded) => Fingerprint::Hash(sha256_hex(encoded.as_bytes())),
        Err(_) => Fingerprint::Unavailable,
    }
}
