use crate::clickhouse::main::encode_rows::encode_rows;
use crate::clickhouse::main::plan_insert::plan_insert;
use crate::clickhouse::main::ttl_mismatches::ttl_mismatches;
use crate::clickhouse::models::{ColumnEncoding, StoredColumn, StoredRow};
use crate::records::main::artifact_rows::artifact_rows;
use crate::records::main::heartbeat_row::heartbeat_row;
use crate::records::models::{ArtifactInput, RecallRow, RowEnvelope};
use crate::schema::main::table_spec::table_spec;
use crate::schema::models::Table;

pub(crate) const BEAT_KEY: &str = "inv-1:2026-10-19T00:00:01.000000Z";
pub(crate) const DETECTED_AT: &str = "2026-10-19T00:00:03.000000Z";
pub(crate) const REFRESH_BEFORE: &str = "2026-10-12T00:00:03.000000Z";

fn envelope() -> RowEnvelope {
    RowEnvelope {
        invocation_id: "inv-1".to_owned(),
        invocation_started_at: "2026-10-19T00:00:00.000000Z".to_owned(),
        producer_version: "test".to_owned(),
    }
}

/// A heartbeat row and the artifact and reference rows of one SQL text.
pub(crate) fn batch() -> Vec<RecallRow> {
    let mut rows: Vec<RecallRow> = vec![heartbeat_row(
        &envelope(),
        ("2026-10-19T00:00:01.000000Z", "2026-10-19T00:01:31.000000Z"),
        (Some("host"), Some(7)),
        (None, None),
    )];
    rows.extend(artifact_rows(
        &envelope(),
        &ArtifactInput {
            digest: "sha256:abc".to_owned(),
            kind: "sql".to_owned(),
            media_type: "text/x-sql".to_owned(),
            content: b"select 1".to_vec(),
            seen_at: "2026-10-19T00:00:02.000000Z".to_owned(),
            role: "executed_sql".to_owned(),
            ref_id: "statement-1".to_owned(),
            statement_id: Some("statement-1".to_owned()),
            resource_id: None,
        },
    ));
    rows
}

/// The content digest the batch's row in `table` carries.
pub(crate) fn batch_hash(table: Table) -> String {
    batch()
        .into_iter()
        .find(|row| row.table == table)
        .and_then(|row| row.content_hash().map(str::to_owned))
        .unwrap_or_default()
}

/// The rows written per table and the conflicts found when the batch meets `stored`.
pub(crate) fn planned(stored: &[StoredRow]) -> (Vec<(&'static str, usize)>, usize) {
    let plan = plan_insert(batch(), stored, (DETECTED_AT, REFRESH_BEFORE));
    let mut written: Vec<(&'static str, usize)> = plan
        .inserts
        .iter()
        .map(|(table, rows)| (table_spec(*table).name, rows.len()))
        .collect();
    written.sort_unstable();
    (written, plan.outcome.conflicts.len())
}

/// A stored key holding one digest.
pub(crate) fn stored(dataset: &str, (key, hash): (&str, &str), newest: Option<&str>) -> StoredRow {
    StoredRow {
        dataset: dataset.to_owned(),
        record_key: key.to_owned(),
        first_hash: hash.to_owned(),
        hashes: vec![hash.to_owned()],
        newest_seen_at: newest.map(str::to_owned),
    }
}

/// The columns and block of the batch's heartbeat written into `columns`.
pub(crate) fn encoded_heartbeat(
    columns: &[(&str, ColumnEncoding, bool)],
    ingested_at_micros: i64,
) -> Result<(Vec<String>, Vec<u8>), String> {
    let columns: Vec<StoredColumn> = columns
        .iter()
        .map(|(name, encoding, nullable)| StoredColumn {
            name: (*name).to_owned(),
            encoding: *encoding,
            nullable: *nullable,
        })
        .collect();
    encode_rows(&batch()[..1], &columns, ingested_at_micros)
}

/// The little-endian bytes of the pieces, in order.
pub(crate) fn block(pieces: &[&[u8]]) -> Vec<u8> {
    pieces.concat()
}

/// The stored TTL days of the first table off `retention_days`, for an output table created by `create_query`.
pub(crate) fn first_mismatch(create_query: &str, retention_days: u32) -> Option<Option<u64>> {
    let relations = [("recall_output".to_owned(), create_query.to_owned())];
    ttl_mismatches(&relations, retention_days)
        .first()
        .map(|mismatch| mismatch.stored_days)
}
