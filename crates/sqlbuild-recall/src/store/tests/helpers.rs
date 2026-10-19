use std::time::{Duration, SystemTime, UNIX_EPOCH};

use tempfile::TempDir;

use crate::records::main::event_object_row::event_object_row;
use crate::records::main::format_timestamp::format_timestamp;
use crate::records::main::output_row::output_row;
use crate::records::main::parse_event::parse_event;
use crate::records::main::parse_timestamp::parse_timestamp;
use crate::records::models::{
    ArtifactInput, DeliveryCounts, OutputChunk, OutputStream, RecallRow, RecallValue, RowEnvelope,
};
use crate::store::errors::{StoreError, StoreErrorKind};
use crate::store::main::ensure_sqlite_schema::ensure_sqlite_schema;
use crate::store::main::insert_rows::insert_rows;
use crate::store::main::maintain_sqlite_store::maintain_sqlite_store;
use crate::store::main::observe_store_file::observe_store_file;
use crate::store::main::open_sqlite_store::open_sqlite_store;
use crate::store::main::quarantine_store::quarantine_store;
use crate::store::main::query_store::query_store;
use crate::store::models::{
    MaintenanceOutcome, MaintenanceRequest, OpenMode, QuarantineOutcome, SqliteStore,
    StoreObservation,
};
use crate::store::tests::test_types::QuarantineRace;

pub(crate) const NOW: &str = "2026-10-19T12:00:00.000000Z";

/// The envelope of invocation `invocation_id` started at `started_at`.
pub(crate) fn envelope(invocation_id: &str, started_at: &str) -> RowEnvelope {
    RowEnvelope {
        invocation_id: invocation_id.to_owned(),
        invocation_started_at: started_at.to_owned(),
        producer_version: "test".to_owned(),
    }
}

/// A store with the current schema in a fresh temporary project.
pub(crate) fn new_store() -> (TempDir, SqliteStore) {
    let directory = tempfile::tempdir().expect("a temporary directory can be created");
    let store = open_sqlite_store(
        &directory.path().join("logs/recall.sqlite3"),
        OpenMode::ReadWrite,
    )
    .expect("the store opens");
    ensure_sqlite_schema(&store, &envelope("setup", NOW), NOW).expect("the schema can be ensured");
    (directory, store)
}

/// Insert `rows` at `NOW`.
pub(crate) fn write(store: &SqliteStore, rows: &[RecallRow]) {
    insert_rows(store, rows, NOW).expect("rows can be inserted");
}

/// One output chunk row.
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
            omitted: None,
        },
    )
}

/// One `x` stdout chunk per sequence.
pub(crate) fn chunks(envelope: &RowEnvelope, sequences: &[u64]) -> Vec<RecallRow> {
    sequences
        .iter()
        .map(|sequence| chunk(envelope, (*sequence, OutputStream::Stdout, b"x")))
        .collect()
}

/// One lifecycle event row; `correlations` is spliced in as extra JSON members.
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
    parse_event(&json)
        .and_then(|event| event_object_row(envelope, &event))
        .expect("the fixture is a valid lifecycle event")
}

/// The result rows of `sql`.
pub(crate) fn rows(store: &SqliteStore, sql: &str) -> Vec<Vec<RecallValue>> {
    query_store(store, sql, None)
        .expect("the query is valid")
        .rows
}

/// The rows `sql` projects after writing each batch in order to a fresh store.
pub(crate) fn projected(batches: &[Vec<RecallRow>], sql: &str) -> Vec<Vec<RecallValue>> {
    let (_directory, store) = new_store();
    for batch in batches {
        write(&store, batch);
    }
    rows(&store, sql)
}

/// A text value.
pub(crate) fn text(value: &str) -> RecallValue {
    RecallValue::Text(value.to_owned())
}

/// An integer value.
pub(crate) fn integer(value: i64) -> RecallValue {
    RecallValue::Integer(value)
}

fn moved(base: SystemTime, seconds: i64) -> String {
    let base_seconds: i64 = base.duration_since(UNIX_EPOCH).map_or(0, |elapsed| {
        i64::try_from(elapsed.as_secs()).unwrap_or(i64::MAX)
    });
    let target: u64 = u64::try_from(base_seconds.saturating_add(seconds)).unwrap_or_default();
    format_timestamp(UNIX_EPOCH + Duration::from_secs(target))
}

/// `NOW` moved by `seconds`.
pub(crate) fn shifted(seconds: i64) -> String {
    moved(
        parse_timestamp(NOW).expect("the timestamp is valid"),
        seconds,
    )
}

/// The real clock moved by `seconds_from_now`.
pub(crate) fn wall_clock(seconds_from_now: i64) -> String {
    moved(SystemTime::now(), seconds_from_now)
}

/// Delivery counts with `filtered`, `dropped` and `delivered` rows.
pub(crate) fn delivered(filtered: u64, dropped: u64, delivered: u64) -> DeliveryCounts {
    DeliveryCounts {
        accepted: delivered + filtered + dropped,
        delivered,
        filtered,
        dropped,
        ..DeliveryCounts::default()
    }
}

/// A SQL artifact `digest` referenced by itself and seen at `seen_at`.
pub(crate) fn artifact(digest: &str, seen_at: &str) -> ArtifactInput {
    ArtifactInput {
        digest: digest.to_owned(),
        kind: "sql".to_owned(),
        media_type: "text/x-sql".to_owned(),
        content: b"select 1".to_vec(),
        seen_at: seen_at.to_owned(),
        ref_id: digest.to_owned(),
        role: "executed_sql".to_owned(),
        statement_id: None,
        resource_id: None,
    }
}

/// Outcomes of maintenance runs at `(offset seconds, budget seconds)` and the rows `sql` keeps.
pub(crate) fn maintained(
    batch: &[RecallRow],
    runs: &[(i64, u64)],
    sql: &str,
) -> (Vec<MaintenanceOutcome>, Vec<Vec<RecallValue>>) {
    let (_directory, store) = new_store();
    write(&store, batch);
    let outcomes: Vec<MaintenanceOutcome> = runs
        .iter()
        .map(|(offset, budget)| {
            let now = shifted(*offset);
            let request = MaintenanceRequest {
                now: parse_timestamp(&now).expect("the timestamp is valid"),
                retention_days: 30,
                owner: "host:1".to_owned(),
                budget: Duration::from_secs(*budget),
                envelope: envelope("maintainer", &now),
            };
            maintain_sqlite_store(&store, &request).expect("maintenance succeeds")
        })
        .collect();
    (outcomes, rows(&store, sql))
}

/// `result` with the error reduced to its kind.
pub(crate) fn error_kind<T>(result: Result<T, StoreError>) -> Result<T, StoreErrorKind> {
    result.map_err(|error| error.kind)
}

/// A store whose recorded schema version is newer, reopened and ensured by this version.
pub(crate) fn newer_schema_store() -> (TempDir, SqliteStore) {
    let (directory, store) = new_store();
    write(
        &store,
        &[crate::records::main::meta_row::meta_row(
            &envelope("newer", NOW),
            ("schema", "schema_version", "99"),
            NOW,
        )],
    );
    store
        .connection
        .execute_batch("DROP VIEW conflicts; CREATE VIEW conflicts AS SELECT 'newer' AS marker")
        .expect("the fixture SQL runs");
    drop(store);
    let path = directory.path().join("logs/recall.sqlite3");
    let reopened = open_sqlite_store(&path, OpenMode::ReadWrite).expect("the store opens");
    ensure_sqlite_schema(&reopened, &envelope("older", NOW), NOW)
        .expect("the schema can be ensured");
    drop(reopened);
    let read_only = open_sqlite_store(&path, OpenMode::ReadOnly).expect("the store opens");
    (directory, read_only)
}

/// The error kind of opening `relative_path` read-write under a read-only directory.
#[cfg(unix)]
pub(crate) fn open_under_locked_directory(relative_path: &str) -> Result<(), StoreErrorKind> {
    use std::os::unix::fs::PermissionsExt;
    let directory = tempfile::tempdir().expect("a temporary directory can be created");
    let locked = directory.path().join("locked");
    std::fs::create_dir(&locked).expect("the test directory can be created");
    std::fs::set_permissions(&locked, std::fs::Permissions::from_mode(0o555))
        .expect("test directory permissions can change");
    let opened = open_sqlite_store(&locked.join(relative_path), OpenMode::ReadWrite);
    std::fs::set_permissions(&locked, std::fs::Permissions::from_mode(0o755))
        .expect("test directory permissions can change");
    error_kind(opened.map(drop))
}

#[cfg(unix)]
fn corrupt_copies(directory: &std::path::Path) -> usize {
    std::fs::read_dir(directory)
        .expect("the directory lists")
        .filter_map(Result::ok)
        .filter(|entry| {
            let name = entry.file_name().to_string_lossy().into_owned();
            name.contains(".corrupt-") && !name.ends_with("-wal") && !name.ends_with("-shm")
        })
        .count()
}

#[cfg(unix)]
/// Nobody else acts on the corrupt file.
pub(crate) fn nobody_else(
    _path: &std::path::Path,
    _observed: &StoreObservation,
    _lock: &std::fs::File,
) {
}

#[cfg(unix)]
/// Another process moves the corrupt file aside and starts a fresh store.
pub(crate) fn already_replaced(
    path: &std::path::Path,
    observed: &StoreObservation,
    _lock: &std::fs::File,
) {
    let give_up = std::time::Instant::now() + Duration::from_millis(100);
    drop(
        quarantine_store(path, observed, (give_up, SystemTime::now()))
            .expect("the first move succeeds"),
    );
    let fresh = open_sqlite_store(path, OpenMode::ReadWrite).expect("a fresh store opens");
    ensure_sqlite_schema(&fresh, &envelope("fresh", NOW), NOW).expect("the fresh store is set up");
}

#[cfg(unix)]
/// Another process holds the quarantine lock.
pub(crate) fn lock_held(
    _path: &std::path::Path,
    _observed: &StoreObservation,
    lock: &std::fs::File,
) {
    rustix::fs::flock(lock, rustix::fs::FlockOperation::LockExclusive).expect("the lock is taken");
}

#[cfg(unix)]
/// Observe a corrupt store, let `race` happen, then move it aside with the now possibly stale observation: whether it moved, how many copies were moved aside, and whether a SQLite store is at the path.
pub(crate) fn quarantine_after(race: QuarantineRace) -> (bool, usize, bool) {
    let directory = tempfile::tempdir().expect("a temporary directory can be created");
    let path = directory.path().join("recall.sqlite3");
    std::fs::write(&path, b"this is not a database").expect("test files can be written");
    std::fs::write(directory.path().join("recall.sqlite3-wal"), b"stale")
        .expect("test files can be written");
    let observed = observe_store_file(&path)
        .expect("the file can be read")
        .expect("the corrupt file is observed");
    let lock = std::fs::File::create(directory.path().join("recall.sqlite3.lock"))
        .expect("the lock file can be created");
    race(&path, &observed, &lock);
    let give_up = std::time::Instant::now() + Duration::from_millis(100);
    let outcome = quarantine_store(&path, &observed, (give_up, SystemTime::now()))
        .expect("the move does not fail");
    let live_store: bool = matches!(
        observe_store_file(&path),
        Ok(Some(current)) if !current.header_foreign
    ) && open_sqlite_store(&path, OpenMode::ReadOnly).is_ok();
    drop(lock);
    (
        matches!(outcome, QuarantineOutcome::Moved(_)),
        corrupt_copies(directory.path()),
        live_store,
    )
}
