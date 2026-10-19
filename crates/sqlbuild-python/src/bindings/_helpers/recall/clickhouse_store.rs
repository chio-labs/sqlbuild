//! The ClickHouse Recall store: written and read through the ClickHouse adapter's connection.

use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant, SystemTime};

use pyo3::prelude::Python;
use sqlbuild_config::models::ConfigValue;
use sqlbuild_recall::clickhouse::constants::{BATCH_ROWS, BATCH_WINDOW_MS};
use sqlbuild_recall::clickhouse::main::deduplication_token::deduplication_token;
use sqlbuild_recall::clickhouse::main::encode_rows::encode_rows;
use sqlbuild_recall::clickhouse::main::parse_column_encoding::parse_column_encoding;
use sqlbuild_recall::clickhouse::main::plan_insert::plan_insert;
use sqlbuild_recall::clickhouse::main::store_state_sql::store_state_sql;
use sqlbuild_recall::clickhouse::main::stored_rows_sql::stored_rows_sql;
use sqlbuild_recall::clickhouse::main::ttl_mismatches::ttl_mismatches;
use sqlbuild_recall::clickhouse::models::{StoredColumn, StoredRow, TtlMismatch};
use sqlbuild_recall::records::main::epoch_micros::epoch_micros;
use sqlbuild_recall::records::main::format_timestamp::format_timestamp;
use sqlbuild_recall::records::main::meta_row::meta_row;
use sqlbuild_recall::records::models::{OutputStream, RecallRow, RecallValue, RowEnvelope};
use sqlbuild_recall::schema::constants::{
    ALL_TABLES, ARTIFACT_REFRESH_DAYS, META_SCHEMA_COMPONENT, META_SCHEMA_VERSION_KEY,
    RECALL_SCHEMA_VERSION, VIEW_NAMES,
};
use sqlbuild_recall::schema::main::add_column_statement::add_column_statement;
use sqlbuild_recall::schema::main::clickhouse_relation::clickhouse_relation;
use sqlbuild_recall::schema::main::retention_fix_statements::retention_fix_statements;
use sqlbuild_recall::schema::main::table_columns::table_columns;
use sqlbuild_recall::schema::main::table_spec::table_spec;
use sqlbuild_recall::schema::main::table_statements::table_statements;
use sqlbuild_recall::schema::main::view_statements::view_statements;
use sqlbuild_recall::schema::models::{ColumnSpec, DdlOptions, Dialect, Table};
use sqlbuild_recall::store::constants::LAST_INVOCATION_SELECTOR;
use sqlbuild_recall::store::errors::{StoreError, StoreErrorKind};
use sqlbuild_recall::store::models::{
    DescribedColumn, DescribedRelation, InsertOutcome, OutputTranscript, QueryResult,
};
use sqlbuild_recall::store::types::{RecallStore, RecallStoreOpener};

use crate::bindings::_helpers::recall::clickhouse_calls::{
    self as calls, QueryStatistics, StoreHandle,
};
use crate::bindings::_helpers::recall::constants::SECONDS_PER_DAY;

/// Where a ClickHouse store lives and how long it keeps history.
#[derive(Clone, Debug)]
pub(crate) struct ClickHouseLocation {
    pub(crate) config: Vec<(String, ConfigValue)>,
    pub(crate) options: DdlOptions,
}

impl ClickHouseLocation {
    pub(crate) fn new(config: &[(String, ConfigValue)], database: &str, retention: u32) -> Self {
        Self {
            config: config.to_vec(),
            options: DdlOptions {
                database: Some(database.to_owned()),
                retention_days: retention,
                cluster: None,
            },
        }
    }

    fn connect_action(&self) -> String {
        format!("connect to the Recall store in `{}`", self.database())
    }

    fn database(&self) -> &str {
        self.options.database.as_deref().unwrap_or_default()
    }

    fn table(&self, name: &str) -> String {
        clickhouse_relation(name, &self.options)
    }
}

/// Opens the store on the delivery thread; `retention_notice` decides whether a retention conflict is reported this time.
#[derive(Debug)]
pub(crate) struct ClickHouseStoreOpener {
    pub(crate) location: ClickHouseLocation,
    pub(crate) retention_notice: fn(&Path, &str) -> bool,
    pub(crate) project_dir: PathBuf,
}

/// The Recall relations present: tables with their `CREATE` queries, views, and the stored schema version.
struct StoreState {
    tables: Vec<(String, String)>,
    views: HashSet<String>,
    version: i64,
}

/// The store the delivery thread writes.
struct ClickHouseStore {
    location: ClickHouseLocation,
    connection: Option<StoreHandle>,
    columns: HashMap<Table, Vec<StoredColumn>>,
    notices: Vec<String>,
}

fn text(value: Option<&RecallValue>) -> String {
    match value {
        Some(RecallValue::Text(text)) => text.clone(),
        Some(RecallValue::Blob(data)) => String::from_utf8_lossy(data).into_owned(),
        Some(RecallValue::Integer(number)) => number.to_string(),
        _ => String::new(),
    }
}

fn integer(value: Option<&RecallValue>) -> i64 {
    match value {
        Some(RecallValue::Integer(number)) => *number,
        _ => 0,
    }
}

/// `text` as a ClickHouse string literal.
fn literal(text: &str) -> String {
    format!("'{}'", text.replace('\\', "\\\\").replace('\'', "\\'"))
}

impl ClickHouseStore {
    fn connection(&self) -> Result<StoreHandle, StoreError> {
        self.connection.ok_or_else(|| StoreError {
            kind: StoreErrorKind::Other,
            message: "the Recall store connection is closed".to_owned(),
        })
    }

    fn query(&self, py: Python<'_>, sql: &str, action: &str) -> Result<QueryResult, StoreError> {
        calls::query(py, self.connection()?, (sql, &[]), action).map(|(result, _)| result)
    }

    fn command(&self, py: Python<'_>, sql: &str, action: &str) -> Result<(), StoreError> {
        calls::command(py, self.connection()?, sql, action)
    }

    /// The Recall relations present, with their `CREATE` queries, and the stored schema version.
    fn state(&self, py: Python<'_>) -> Result<StoreState, StoreError> {
        let sql = store_state_sql(self.location.database());
        let relations: QueryResult = self.query(py, &sql.relations, "inspect the Recall store")?;
        let mut tables: Vec<(String, String)> = Vec::new();
        let mut views: HashSet<String> = HashSet::new();
        for row in &relations.rows {
            let name = text(row.first());
            if integer(row.get(1)) == 1 {
                views.insert(name);
            } else {
                tables.push((name, text(row.get(2))));
            }
        }
        let version: i64 = if tables
            .iter()
            .any(|(name, _)| name == table_spec(Table::Meta).name)
        {
            let found = self.query(py, &sql.schema_version, "read the Recall schema version")?;
            integer(found.rows.first().and_then(|row| row.first()))
        } else {
            0
        };
        Ok(StoreState {
            tables,
            views,
            version,
        })
    }

    fn require_database(&self, py: Python<'_>) -> Result<(), StoreError> {
        let found = self.query(
            py,
            &format!(
                "SELECT count() FROM system.databases WHERE name = {}",
                literal(self.location.database())
            ),
            "inspect the Recall store",
        )?;
        if integer(found.rows.first().and_then(|row| row.first())) == 0 {
            return Err(StoreError {
                kind: StoreErrorKind::NotFound,
                message: format!(
                    "ClickHouse database `{}` does not exist; Recall creates its tables only in an \
                     existing database",
                    self.location.database()
                ),
            });
        }
        Ok(())
    }

    fn read_columns(&mut self, py: Python<'_>) -> Result<(), StoreError> {
        let sql = store_state_sql(self.location.database());
        let found = self.query(py, &sql.columns, "inspect the Recall tables")?;
        let mut columns: HashMap<Table, Vec<StoredColumn>> = HashMap::new();
        for row in &found.rows {
            let table_name = text(row.first());
            let Some(table) = ALL_TABLES
                .iter()
                .find(|table| table_spec(**table).name == table_name)
            else {
                continue;
            };
            let name = text(row.get(1));
            let type_text = text(row.get(2));
            let (encoding, nullable) = parse_column_encoding(&type_text).ok_or_else(|| StoreError {
                kind: StoreErrorKind::Other,
                message: format!(
                    "Recall column {table_name}.{name} has type {type_text}, which Recall does not \
                     write"
                ),
            })?;
            columns.entry(*table).or_default().push(StoredColumn {
                name,
                encoding,
                nullable,
            });
        }
        self.columns = columns;
        Ok(())
    }

    /// Create missing tables, add missing columns and replace the views when this build's schema is newer; a newer store keeps its views.
    fn ensure_schema(
        &mut self,
        py: Python<'_>,
        envelope: &RowEnvelope,
    ) -> Result<Vec<(String, String)>, StoreError> {
        let StoreState {
            tables,
            views,
            version,
        } = self.state(py)?;
        let complete: bool = tables.len() == ALL_TABLES.len() && views.len() == VIEW_NAMES.len();
        if complete && version >= RECALL_SCHEMA_VERSION {
            self.read_columns(py)?;
            return Ok(tables);
        }
        if complete && version == 0 {
            self.read_columns(py)?;
            if self.missing_columns().is_empty() {
                self.record_version(py, envelope)?;
                return Ok(tables);
            }
        }
        self.require_database(py)?;
        for statement in table_statements(Dialect::ClickHouse, &self.location.options) {
            self.command(py, &statement, "create the Recall tables")?;
        }
        self.read_columns(py)?;
        for (table, column) in self.missing_columns() {
            let statement = add_column_statement(
                Dialect::ClickHouse,
                &self.location.options,
                (table_spec(table), &column),
            );
            self.command(py, &statement, "add a Recall column")?;
        }
        self.read_columns(py)?;
        let upgrade: bool = version < RECALL_SCHEMA_VERSION;
        for (name, statement) in view_statements(Dialect::ClickHouse, &self.location.options) {
            if upgrade {
                self.command(py, &statement, "create the Recall views")?;
            } else if !views.contains(name) {
                let statement =
                    statement.replacen("CREATE OR REPLACE VIEW", "CREATE VIEW IF NOT EXISTS", 1);
                self.command(py, &statement, "create the Recall views")?;
            }
        }
        if upgrade {
            self.record_version(py, envelope)?;
        }
        Ok(self.state(py)?.tables)
    }

    /// Every column this build writes that the stored tables lack.
    fn missing_columns(&self) -> Vec<(Table, ColumnSpec)> {
        let mut missing: Vec<(Table, ColumnSpec)> = Vec::new();
        for table in ALL_TABLES {
            let present: &[StoredColumn] = self.columns.get(&table).map_or(&[], Vec::as_slice);
            for column in table_columns(table) {
                if !present.iter().any(|stored| stored.name == column.name) {
                    missing.push((table, column));
                }
            }
        }
        missing
    }

    /// Record this build's schema version with an insert, which a writer allowed only `SELECT` and `INSERT` may run.
    fn record_version(&self, py: Python<'_>, envelope: &RowEnvelope) -> Result<(), StoreError> {
        let now = format_timestamp(SystemTime::now());
        let row = meta_row(
            envelope,
            (
                META_SCHEMA_COMPONENT,
                META_SCHEMA_VERSION_KEY,
                &RECALL_SCHEMA_VERSION.to_string(),
            ),
            &now,
        );
        self.write(py, Table::Meta, &[row], SystemTime::now())
    }

    fn write(
        &self,
        py: Python<'_>,
        table: Table,
        rows: &[RecallRow],
        now: SystemTime,
    ) -> Result<(), StoreError> {
        let columns: &[StoredColumn] = self.columns.get(&table).map_or(&[], Vec::as_slice);
        let micros: i64 = epoch_micros(now);
        let (names, block) = encode_rows(rows, columns, micros).map_err(|message| StoreError {
            kind: StoreErrorKind::Other,
            message,
        })?;
        calls::insert(
            py,
            self.connection()?,
            (&self.location.table(table_spec(table).name), &names, &block),
            &deduplication_token(rows),
        )
    }

    fn stored_rows(
        &self,
        py: Python<'_>,
        rows: &[RecallRow],
    ) -> Result<Vec<StoredRow>, StoreError> {
        let Some(sql) = stored_rows_sql(rows, &self.location.options) else {
            return Ok(Vec::new());
        };
        let found = self.query(py, &sql, "read stored Recall rows")?;
        Ok(found
            .rows
            .iter()
            .map(|row| {
                let hashes: Vec<String> = text(row.get(3)).split(',').map(str::to_owned).collect();
                let newest: String = text(row.get(4));
                StoredRow {
                    dataset: text(row.first()),
                    record_key: text(row.get(1)),
                    first_hash: text(row.get(2)),
                    hashes,
                    newest_seen_at: (!newest.is_empty()).then_some(newest),
                }
            })
            .collect())
    }

    fn retention_conflict(&self, tables: &[(String, String)]) -> Option<String> {
        let mismatches: Vec<TtlMismatch> =
            ttl_mismatches(tables, self.location.options.retention_days);
        let first: &TtlMismatch = mismatches.first()?;
        let stored: String = first
            .stored_days
            .map_or_else(|| "no day TTL".to_owned(), |days| format!("{days} days"));
        Some(format!(
            "the ClickHouse store in `{}` keeps history for {stored} by its table TTLs, but this \
             project is configured for {} days; retention is a store-wide policy and Recall never \
             changes TTLs itself. An administrator can apply the configured retention with:\n\n{}",
            self.location.database(),
            self.location.options.retention_days,
            retention_fix_statements(
                &mismatches
                    .iter()
                    .map(|mismatch| mismatch.table.clone())
                    .collect::<Vec<_>>(),
                &self.location.options
            )
        ))
    }
}

impl RecallStore for ClickHouseStore {
    fn insert(&self, rows: &[RecallRow], _give_up: Instant) -> Result<InsertOutcome, StoreError> {
        Python::attach(|py| {
            let now: SystemTime = SystemTime::now();
            let refresh_before: SystemTime = now
                .checked_sub(Duration::from_secs(
                    u64::from(ARTIFACT_REFRESH_DAYS) * SECONDS_PER_DAY,
                ))
                .unwrap_or(SystemTime::UNIX_EPOCH);
            let stored: Vec<StoredRow> = self.stored_rows(py, rows)?;
            let plan = plan_insert(
                rows.to_vec(),
                &stored,
                (&format_timestamp(now), &format_timestamp(refresh_before)),
            );
            let mut outcome: InsertOutcome = plan.outcome;
            for (table, table_rows) in &plan.inserts {
                match self.write(py, *table, table_rows, now) {
                    Ok(()) => {}
                    Err(error) if error.kind == StoreErrorKind::Busy => return Err(error),
                    Err(error) => {
                        outcome.failed.push(*table);
                        outcome.failure.get_or_insert(error.message);
                    }
                }
            }
            let failed: &[Table] = &outcome.failed;
            outcome
                .delivered
                .retain(|(table, _)| !failed.contains(table));
            Ok(outcome)
        })
    }

    fn take_notices(&mut self) -> Vec<String> {
        std::mem::take(&mut self.notices)
    }

    fn close(&mut self) {
        if let Some(connection) = self.connection.take() {
            Python::attach(|py| calls::close(py, connection));
        }
    }
}

impl RecallStoreOpener for ClickHouseStoreOpener {
    fn open(
        &self,
        envelope: &RowEnvelope,
        _give_up: Instant,
    ) -> Result<Box<dyn RecallStore>, StoreError> {
        Python::attach(|py| {
            let mut store = ClickHouseStore {
                location: self.location.clone(),
                connection: Some(calls::connect(
                    py,
                    &self.location.config,
                    &self.location.connect_action(),
                )?),
                columns: HashMap::new(),
                notices: Vec::new(),
            };
            match store.ensure_schema(py, envelope) {
                Ok(tables) => {
                    if let Some(notice) = store.retention_conflict(&tables)
                        && (self.retention_notice)(
                            &self.project_dir,
                            &format!("{}:retention", self.location.database()),
                        )
                    {
                        store.notices.push(notice);
                    }
                    Ok(Box::new(store) as Box<dyn RecallStore>)
                }
                Err(error) => {
                    store.close();
                    Err(error)
                }
            }
        })
    }

    fn batch_rows(&self) -> usize {
        BATCH_ROWS
    }

    fn batch_window(&self) -> Duration {
        Duration::from_millis(BATCH_WINDOW_MS)
    }
}

/// A ClickHouse store opened for `sqb recall`.
pub(crate) struct ClickHouseReader {
    store: ClickHouseStore,
}

impl ClickHouseReader {
    pub(crate) fn open(py: Python<'_>, location: &ClickHouseLocation) -> Result<Self, StoreError> {
        let mut store = ClickHouseStore {
            location: location.clone(),
            connection: Some(calls::connect(
                py,
                &location.config,
                &location.connect_action(),
            )?),
            columns: HashMap::new(),
            notices: Vec::new(),
        };
        let state: StoreState = store.state(py)?;
        if state.tables.len() < ALL_TABLES.len() || state.views.len() < VIEW_NAMES.len() {
            store.close();
            return Err(StoreError {
                kind: StoreErrorKind::NotFound,
                message: format!(
                    "no Recall history is recorded yet in ClickHouse database `{}`, or its tables \
                     are still being created; run a command first",
                    location.database()
                ),
            });
        }
        Ok(Self { store })
    }

    /// The database the store lives in.
    pub(crate) fn database(&self) -> &str {
        self.store.location.database()
    }

    /// At most `limit` rows of a read-only query, with the server's statistics.
    pub(crate) fn query(
        &self,
        py: Python<'_>,
        sql: &str,
        limit: Option<usize>,
    ) -> Result<(QueryResult, QueryStatistics), StoreError> {
        let mut settings: Vec<(&str, i64)> = vec![("readonly", 2)];
        if let Some(limit) = limit {
            settings.push(("limit", i64::try_from(limit).unwrap_or(i64::MAX - 1) + 1));
        }
        let (mut result, statistics) = calls::query(
            py,
            self.store.connection()?,
            (sql, &settings),
            "run the Recall query",
        )
        .map_err(|failure| StoreError {
            kind: if failure.kind == StoreErrorKind::Busy {
                StoreErrorKind::Other
            } else {
                StoreErrorKind::Query
            },
            message: failure.message,
        })?;
        if let Some(limit) = limit
            && result.rows.len() > limit
        {
            result.rows.truncate(limit);
            result.truncated = true;
        }
        Ok((result, statistics))
    }

    /// The store's views, then its tables, with their columns.
    pub(crate) fn describe(&self, py: Python<'_>) -> Result<Vec<DescribedRelation>, StoreError> {
        let names: Vec<String> = VIEW_NAMES
            .iter()
            .map(|name| literal(name))
            .chain(
                ALL_TABLES
                    .iter()
                    .map(|table| literal(table_spec(*table).name)),
            )
            .collect();
        let found = self.store.query(
            py,
            &format!(
                "SELECT c.table, if(t.engine = 'View', 'view', 'table') AS kind, c.name, c.type \
                 FROM system.columns AS c INNER JOIN system.tables AS t \
                 ON t.database = c.database AND t.name = c.table \
                 WHERE c.database = {} AND c.table IN ({}) \
                 ORDER BY kind = 'table', c.table, c.position",
                literal(self.database()),
                names.join(", ")
            ),
            "describe the Recall store",
        )?;
        let mut relations: Vec<DescribedRelation> = Vec::new();
        for row in &found.rows {
            let name = text(row.first());
            if relations.last().is_none_or(|last| last.name != name) {
                relations.push(DescribedRelation {
                    name,
                    kind: text(row.get(1)),
                    columns: Vec::new(),
                });
            }
            let declared_type = text(row.get(3));
            if let Some(relation) = relations.last_mut() {
                relation.columns.push(DescribedColumn {
                    name: text(row.get(2)),
                    nullable: declared_type.starts_with("Nullable("),
                    declared_type,
                });
            }
        }
        Ok(relations)
    }

    /// The full invocation ID an ID, unique prefix or `last` names.
    pub(crate) fn resolve_invocation(
        &self,
        py: Python<'_>,
        selector: &str,
    ) -> Result<String, StoreError> {
        let table = self
            .store
            .location
            .table(table_spec(Table::Invocations).name);
        let sql = if selector == LAST_INVOCATION_SELECTOR {
            format!(
                "SELECT invocation_id FROM {table} \
                 ORDER BY invocation_started_at DESC, invocation_id DESC LIMIT 1"
            )
        } else {
            format!(
                "SELECT DISTINCT invocation_id FROM {table} \
                 WHERE startsWith(invocation_id, {}) ORDER BY invocation_id LIMIT 3",
                literal(selector)
            )
        };
        let found = self.store.query(py, &sql, "find the invocation")?;
        let candidates: Vec<String> = found.rows.iter().map(|row| text(row.first())).collect();
        if let Some(exact) = candidates.iter().find(|candidate| *candidate == selector) {
            return Ok(exact.clone());
        }
        match candidates.as_slice() {
            [] => Err(StoreError {
                kind: StoreErrorKind::NotFound,
                message: if selector == LAST_INVOCATION_SELECTOR {
                    "no invocations are recorded yet".to_owned()
                } else {
                    format!("no recorded invocation matches '{selector}'")
                },
            }),
            [only] => Ok(only.clone()),
            several => Err(StoreError {
                kind: StoreErrorKind::Ambiguous,
                message: format!(
                    "'{selector}' matches several invocations: {}{}",
                    several[..2].join(", "),
                    if several.len() > 2 { ", …" } else { "" }
                ),
            }),
        }
    }

    /// One invocation's exact output bytes, deduplicated by sequence, and its completeness.
    pub(crate) fn read_output_transcript(
        &self,
        py: Python<'_>,
        invocation_id: &str,
        stream: Option<OutputStream>,
    ) -> Result<OutputTranscript, StoreError> {
        let id = literal(invocation_id);
        let stream_filter: String = stream.map_or_else(String::new, |stream| {
            format!(" AND stream = {}", literal(stream.as_str()))
        });
        let output = self.store.location.table(table_spec(Table::Output).name);
        let chunks = self.store.query(
            py,
            &format!(
                "SELECT data FROM (SELECT sequence, stream, data FROM {output} \
                 WHERE invocation_id = {id} ORDER BY sequence, ingested_at LIMIT 1 BY sequence) \
                 WHERE 1{stream_filter} ORDER BY sequence"
            ),
            "read Recall output",
        )?;
        let mut transcript = OutputTranscript {
            invocation_id: invocation_id.to_owned(),
            ..OutputTranscript::default()
        };
        for row in &chunks.rows {
            match row.first() {
                Some(RecallValue::Blob(data)) => transcript.data.extend_from_slice(data),
                Some(RecallValue::Text(text)) => transcript.data.extend_from_slice(text.as_bytes()),
                _ => {}
            }
        }
        let database = self.store.location.table("invocations");
        let status = self.store.query(
            py,
            &format!("SELECT status FROM {database} WHERE invocation_id = {id}"),
            "read the Recall invocation",
        )?;
        transcript.status = status.rows.first().map(|row| text(row.first()));
        let completeness_view = self.store.location.table("output_invocations");
        let completeness = self.store.query(
            py,
            &format!(
                "SELECT missing_sequences, reported_drops, filtered, flush_complete, complete, \
                 gap_reason FROM {completeness_view} WHERE invocation_id = {id}"
            ),
            "read Recall output completeness",
        )?;
        if let Some(row) = completeness.rows.first() {
            transcript.missing_sequences = integer(row.first());
            transcript.reported_drops = integer(row.get(1));
            transcript.filtered = integer(row.get(2));
            transcript.flush_complete = integer(row.get(3)) != 0;
            transcript.complete = integer(row.get(4)) != 0;
            let reason = text(row.get(5));
            transcript.gap_reason = (!reason.is_empty()).then_some(reason);
        }
        Ok(transcript)
    }

    pub(crate) fn close(mut self) {
        self.store.close();
    }
}
