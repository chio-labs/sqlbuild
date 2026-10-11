//! `write_cached_scope_index`'s envelope of one full scope index.

use sqlbuild_core::json::models::JsonValue;

use crate::scope_cache::_helpers::json::{canonical_json, integer, object, sha256_hex, text};
use crate::scope_cache::_helpers::payload::{Unwritable, index_payload};
use crate::scope_cache::constants::CACHE_SCHEMA_VERSION;
use crate::scope_cache::models::{CachedIndex, Unencodable};
use crate::scope_index::main::report_lookup::report_lookup;
use crate::scope_index::models::{ReportDiagnosticKey, ReportLookup, ReportRecords, ReportUsage};

/// The canonical envelope bytes, or `Unencodable` when Python would skip the write.
pub fn encode_scope_cache(index: &CachedIndex, fingerprint: &str) -> Result<Vec<u8>, Unencodable> {
    let records: ReportRecords = ReportRecords {
        roots: index.roots.clone(),
        resources: index.resources.clone(),
        declarations: index
            .declarations
            .iter()
            .map(|item| item.record.clone())
            .collect(),
        usages: index
            .usages
            .iter()
            .map(|item| ReportUsage {
                consumer: item.consumer.clone(),
                declaration: item.declaration.clone(),
                kind: item.kind.clone(),
                through: item.through.clone(),
            })
            .collect(),
        grants: index.grants.clone(),
        diagnostics: index
            .diagnostics
            .iter()
            .map(|item| ReportDiagnosticKey {
                path: item.path.clone(),
                line: item.line,
                column: item.column,
                code: item.code.clone(),
            })
            .collect(),
    };
    let lookup: ReportLookup = report_lookup(&records).map_err(|_| Unencodable)?;
    let payload: JsonValue = index_payload(index, &lookup).map_err(|Unwritable| Unencodable)?;
    let encoded: String = canonical_json(&payload).map_err(|_| Unencodable)?;
    let digest: String = sha256_hex(encoded.as_bytes());
    let envelope: JsonValue = object(vec![
        ("input_fingerprint", text(fingerprint)),
        ("payload", payload),
        ("payload_sha256", text(&digest)),
        ("schema_version", integer(CACHE_SCHEMA_VERSION)),
    ]);
    canonical_json(&envelope)
        .map(String::into_bytes)
        .map_err(|_| Unencodable)
}
