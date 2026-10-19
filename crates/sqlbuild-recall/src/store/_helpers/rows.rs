//! Idempotent row writes: insert once, compare content on a duplicate key, record conflicts.

use std::collections::hash_map::Entry;
use std::collections::{HashMap, HashSet};

use rusqlite::{Connection, OptionalExtension};

use crate::records::main::conflict_row::conflict_row;
use crate::records::models::{RecallRow, RecallValue, RowEnvelope};
use crate::schema::main::table_spec::table_spec;
use crate::schema::models::Table;
use crate::store::_helpers::schema::stored_columns;
use crate::store::_helpers::sqlite::{SqlValue, checked};
use crate::store::errors::StoreError;
use crate::store::models::{ConflictEvidence, InsertOutcome};

fn key_text(value: Option<&RecallValue>) -> String {
    match value {
        Some(RecallValue::Text(text)) => text.clone(),
        Some(RecallValue::Integer(number)) => number.to_string(),
        Some(RecallValue::Real(number)) => number.to_string(),
        Some(RecallValue::Blob(_)) => "<blob>".to_owned(),
        Some(RecallValue::Null) | None => String::new(),
    }
}

fn text_of(row: &RecallRow, column: &str) -> String {
    key_text(row.value(column))
}

/// Insert one row's values for the columns its table has; `Some(evidence)` when its key holds different content.
fn write_row(
    connection: &Connection,
    (row, columns): (&RecallRow, &HashSet<String>),
    ingested_at: &str,
) -> Result<Option<ConflictEvidence>, StoreError> {
    let spec = table_spec(row.table);
    let ingested: RecallValue = RecallValue::Text(ingested_at.to_owned());
    let stored: Vec<&(&str, RecallValue)> = row
        .values
        .iter()
        .filter(|(name, _)| columns.contains(*name))
        .collect();
    let mut names: Vec<&str> = stored.iter().map(|(name, _)| *name).collect();
    names.push("ingested_at");
    let placeholders: Vec<String> = (1..=names.len()).map(|index| format!("?{index}")).collect();
    let sql = format!(
        "INSERT INTO \"{}\" ({}) VALUES ({}) ON CONFLICT DO NOTHING",
        spec.name,
        names.join(", "),
        placeholders.join(", ")
    );
    let parameters: Vec<SqlValue<'_>> = stored
        .iter()
        .map(|(_, value)| SqlValue(value))
        .chain(std::iter::once(SqlValue(&ingested)))
        .collect();
    let mut statement = checked(connection.prepare_cached(&sql), "prepare Recall insert")?;
    let changed: usize = checked(
        statement.execute(rusqlite::params_from_iter(parameters.iter())),
        "write Recall rows",
    )?;
    if changed > 0 {
        return Ok(None);
    }
    let condition: Vec<String> = spec
        .key
        .iter()
        .enumerate()
        .map(|(index, name)| format!("{name} = ?{}", index + 1))
        .collect();
    let lookup = format!(
        "SELECT content_hash FROM \"{}\" WHERE {}",
        spec.name,
        condition.join(" AND ")
    );
    let null = RecallValue::Null;
    let key_values: Vec<SqlValue<'_>> = spec
        .key
        .iter()
        .map(|name| SqlValue(row.value(name).unwrap_or(&null)))
        .collect();
    let mut statement = checked(connection.prepare_cached(&lookup), "prepare Recall lookup")?;
    let existing: Option<String> = checked(
        statement
            .query_row(rusqlite::params_from_iter(key_values.iter()), |found| {
                found.get(0)
            })
            .optional(),
        "read stored Recall row",
    )?;
    let rejected: &str = row.content_hash().unwrap_or_default();
    match existing {
        Some(existing) if existing != rejected => Ok(Some(ConflictEvidence {
            table: row.table,
            record_key: spec
                .key
                .iter()
                .map(|name| key_text(row.value(name)))
                .collect::<Vec<_>>()
                .join(":"),
            existing_sha256: existing,
            rejected_sha256: rejected.to_owned(),
        })),
        _ => Ok(None),
    }
}

/// Write `rows` on the current transaction; conflicts become `recall_conflicts` rows.
pub(crate) fn write_rows(
    connection: &Connection,
    rows: &[RecallRow],
    ingested_at: &str,
) -> Result<InsertOutcome, StoreError> {
    let mut outcome = InsertOutcome::default();
    let mut columns: HashMap<Table, HashSet<String>> = HashMap::new();
    for row in rows.iter().map(|row| row.table).chain([Table::Conflicts]) {
        if let Entry::Vacant(entry) = columns.entry(row) {
            entry.insert(stored_columns(connection, row)?);
        }
    }
    for row in rows {
        match write_row(connection, (row, &columns[&row.table]), ingested_at)? {
            None => match outcome
                .delivered
                .iter_mut()
                .find(|(seen, _)| *seen == row.table)
            {
                Some((_, count)) => *count += 1,
                None => outcome.delivered.push((row.table, 1)),
            },
            Some(evidence) => {
                let envelope = RowEnvelope {
                    invocation_id: text_of(row, "invocation_id"),
                    invocation_started_at: text_of(row, "invocation_started_at"),
                    producer_version: text_of(row, "producer_version"),
                };
                let conflict = conflict_row(
                    &envelope,
                    (table_spec(row.table).name, &evidence.record_key),
                    (&evidence.existing_sha256, &evidence.rejected_sha256),
                    ingested_at,
                );
                if row.table != Table::Conflicts {
                    write_row(
                        connection,
                        (&conflict, &columns[&Table::Conflicts]),
                        ingested_at,
                    )?;
                }
                outcome.conflicts.push(evidence);
            }
        }
    }
    Ok(outcome)
}
