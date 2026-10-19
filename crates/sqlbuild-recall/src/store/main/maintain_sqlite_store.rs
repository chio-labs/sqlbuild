//! `maintain_sqlite_store`: claimed, budgeted retention deletes and space reclamation.

use std::time::{Duration, Instant, SystemTime};

use rusqlite::Connection;

use crate::records::main::format_timestamp::format_timestamp;
use crate::records::main::meta_row::meta_row;
use crate::records::main::parse_timestamp::parse_timestamp;
use crate::schema::constants::{
    META_MAINTENANCE_CLAIM_KEY, META_MAINTENANCE_COMPONENT, RETENTION_BATCH_INVOCATIONS,
};
use crate::schema::main::sqlite_retention_sql::sqlite_retention_sql;
use crate::store::_helpers::rows::write_rows;
use crate::store::_helpers::sqlite::{checked, immediate};
use crate::store::constants::{
    INCREMENTAL_VACUUM_PAGES, MAINTENANCE_INTERVAL_SECONDS, META_MAINTENANCE_OVERDUE_KEY,
};
use crate::store::errors::StoreError;
use crate::store::models::{MaintenanceOutcome, MaintenanceRequest, SqliteStore};

fn latest(connection: &Connection, key: &str) -> Result<Option<String>, StoreError> {
    checked(
        connection.query_row(
            "SELECT MAX(recorded_at) FROM recall_meta WHERE component = ?1 AND key = ?2",
            [META_MAINTENANCE_COMPONENT, key],
            |row| row.get(0),
        ),
        "read Recall maintenance state",
    )
}

/// Whether this process should maintain now: no recent claim, or the last run left work.
fn due(connection: &Connection, now: SystemTime) -> Result<bool, StoreError> {
    let Some(claim) = latest(connection, META_MAINTENANCE_CLAIM_KEY)? else {
        return Ok(true);
    };
    if latest(connection, META_MAINTENANCE_OVERDUE_KEY)?.is_some_and(|overdue| overdue >= claim) {
        return Ok(true);
    }
    let claimed: SystemTime = parse_timestamp(&claim).unwrap_or(SystemTime::UNIX_EPOCH);
    Ok(now
        .duration_since(claimed)
        .is_ok_and(|elapsed| elapsed >= Duration::from_secs(MAINTENANCE_INTERVAL_SECONDS)))
}

/// Delete invocations started before the retention cutoff, at most once per interval across processes, in short batches within the budget, then reclaim pages and checkpoint the WAL.
pub fn maintain_sqlite_store(
    store: &SqliteStore,
    request: &MaintenanceRequest,
) -> Result<MaintenanceOutcome, StoreError> {
    let started = Instant::now();
    let now_text: String = format_timestamp(request.now);
    let claimed: bool = immediate(
        &store.connection,
        "claim Recall maintenance",
        |connection| {
            if !due(connection, request.now)? {
                return Ok(false);
            }
            write_rows(
                connection,
                &[meta_row(
                    &request.envelope,
                    (
                        META_MAINTENANCE_COMPONENT,
                        META_MAINTENANCE_CLAIM_KEY,
                        &request.owner,
                    ),
                    &now_text,
                )],
                &now_text,
            )?;
            Ok(true)
        },
    )?;
    if !claimed {
        return Ok(MaintenanceOutcome::default());
    }
    let retention = Duration::from_secs(u64::from(request.retention_days) * 86_400);
    let cutoff: String = format_timestamp(
        request
            .now
            .checked_sub(retention)
            .unwrap_or(SystemTime::UNIX_EPOCH),
    );
    let sql = sqlite_retention_sql();
    let mut outcome = MaintenanceOutcome {
        ran: true,
        ..MaintenanceOutcome::default()
    };
    loop {
        if started.elapsed() >= request.budget {
            break;
        }
        let deleted: usize =
            immediate(&store.connection, "apply Recall retention", |connection| {
                let mut statement = checked(
                    connection.prepare_cached(&sql.expired_invocations),
                    "find expired Recall invocations",
                )?;
                let ids: Vec<String> = checked(
                    statement
                        .query_map(
                            rusqlite::params![cutoff, now_text, RETENTION_BATCH_INVOCATIONS],
                            |row| row.get(0),
                        )
                        .and_then(Iterator::collect),
                    "find expired Recall invocations",
                )?;
                if ids.is_empty() {
                    return Ok(0);
                }
                let encoded: String = serde_json::Value::from(ids.clone()).to_string();
                for (_, delete) in &sql.delete_invocations {
                    checked(
                        connection.execute(delete, [&encoded]),
                        "delete expired Recall rows",
                    )?;
                }
                Ok(ids.len())
            })?;
        if deleted == 0 {
            outcome.complete = true;
            break;
        }
        outcome.deleted_invocations += deleted as u64;
    }
    outcome.deleted_artifacts = checked(
        store
            .connection
            .execute(&sql.delete_orphan_artifacts, [&cutoff]),
        "delete unreferenced Recall artifacts",
    )? as u64;
    checked(
        store.connection.execute(&sql.delete_old_claims, [&cutoff]),
        "delete old Recall maintenance claims",
    )?;
    if !outcome.complete {
        immediate(
            &store.connection,
            "record overdue maintenance",
            |connection| {
                write_rows(
                    connection,
                    &[meta_row(
                        &request.envelope,
                        (
                            META_MAINTENANCE_COMPONENT,
                            META_MAINTENANCE_OVERDUE_KEY,
                            &request.owner,
                        ),
                        &now_text,
                    )],
                    &now_text,
                )
                .map(drop)
            },
        )?;
    }
    checked(
        store.connection.execute_batch(&format!(
            "PRAGMA incremental_vacuum({INCREMENTAL_VACUUM_PAGES})"
        )),
        "reclaim Recall pages",
    )?;
    checked(
        store
            .connection
            .query_row("PRAGMA wal_checkpoint(PASSIVE)", [], |_| Ok(())),
        "checkpoint Recall WAL",
    )?;
    Ok(outcome)
}
