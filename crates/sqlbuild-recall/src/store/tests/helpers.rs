use std::time::{Duration, SystemTime};

use tempfile::TempDir;

use crate::records::main::event_row::event_row;
use crate::records::main::format_timestamp::format_timestamp;
use crate::records::main::output_row::output_row;
use crate::records::models::{OutputChunk, OutputStream, RecallRow, RecallValue, RowEnvelope};
use crate::store::main::ensure_sqlite_schema::ensure_sqlite_schema;
use crate::store::main::insert_rows::insert_rows;
use crate::store::main::open_sqlite_store::open_sqlite_store;
use crate::store::main::query_store::query_store;
use crate::store::models::{OpenMode, SqliteStore};

pub(crate) const NOW: &str = "2026-10-19T12:00:00.000000Z";

pub(crate) fn envelope(invocation_id: &str, started_at: &str) -> RowEnvelope {
    RowEnvelope {
        invocation_id: invocation_id.to_owned(),
        invocation_started_at: started_at.to_owned(),
        producer_version: "test".to_owned(),
    }
}

pub(crate) fn new_store() -> (TempDir, SqliteStore) {
    let directory = tempfile::tempdir().expect("temporary directory");
    let store = open_sqlite_store(
        &directory.path().join("logs/recall.sqlite3"),
        OpenMode::ReadWrite,
    )
    .expect("store opens");
    ensure_sqlite_schema(&store, &envelope("setup", NOW), NOW).expect("schema");
    (directory, store)
}

pub(crate) fn write(store: &SqliteStore, rows: &[RecallRow]) {
    insert_rows(store, rows, NOW).expect("rows written");
}

pub(crate) fn chunk(
    envelope: &RowEnvelope,
    (sequence, stream, data): (u64, OutputStream, &[u8]),
) -> RecallRow {
    output_row(
        envelope,
        &OutputChunk {
            sequence,
            stream,
            occurred_at: NOW.to_owned(),
            data: data.to_vec(),
            byte_offset: 0,
            dropped_before: 0,
        },
    )
}

pub(crate) fn event(
    envelope: &RowEnvelope,
    (event_id, event_type, sequence): (&str, &str, i64),
    correlations: &str,
    payload: &str,
) -> RecallRow {
    let json = format!(
        r#"{{"event_id":"{event_id}","event_type":"{event_type}","schema_version":2,
        "producer":"sqlbuild","producer_version":"1","occurred_at":"{NOW}",
        "invocation_id":"{}","invocation_sequence":{sequence}{correlations},"payload":{payload}}}"#,
        envelope.invocation_id
    );
    event_row(envelope, &json).expect("event row")
}

pub(crate) fn rows(store: &SqliteStore, sql: &str) -> Vec<Vec<RecallValue>> {
    query_store(store, sql, None).expect("query").rows
}

pub(crate) fn text(value: &str) -> RecallValue {
    RecallValue::Text(value.to_owned())
}

pub(crate) fn shifted(seconds: i64) -> String {
    let now = crate::records::main::parse_timestamp::parse_timestamp(NOW).expect("now");
    let moved: SystemTime = if seconds >= 0 {
        now + Duration::from_secs(seconds.unsigned_abs())
    } else {
        now - Duration::from_secs(seconds.unsigned_abs())
    };
    format_timestamp(moved)
}

pub(crate) fn wall_clock(seconds_from_now: i64) -> String {
    let now = SystemTime::now();
    let moved = if seconds_from_now >= 0 {
        now + Duration::from_secs(seconds_from_now.unsigned_abs())
    } else {
        now - Duration::from_secs(seconds_from_now.unsigned_abs())
    };
    format_timestamp(moved)
}
