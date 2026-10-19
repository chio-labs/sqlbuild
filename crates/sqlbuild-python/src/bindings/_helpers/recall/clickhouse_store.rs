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

/// A store ready to write: its tables with their `CREATE` queries, and the column additions an administrator must run.
struct ReadyStore {
    tables: Vec<(String, String)>,
    refused_columns: Vec<String>,
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

    /// Create a store whose tables are missing; on existing tables add missing columns where allowed, create missing views, and replace views only on a version upgrade.
    fn ensure_schema(
        &mut self,
        py: Python<'_>,
        envelope: &RowEnvelope,
    ) -> Result<ReadyStore, StoreError> {
        let StoreState {
            tables,
            views,
            version,
        } = self.state(py)?;
        if tables.len() < ALL_TABLES.len() {
            self.create(py, envelope, &views)?;
            return Ok(ReadyStore {
                tables: self.state(py)?.tables,
                refused_columns: Vec::new(),
            });
        }
        self.read_columns(py)?;
        let refused: Vec<String> = self.add_columns(py)?;
        let upgrade: bool = version > 0 && version < RECALL_SCHEMA_VERSION;
        let views_due: bool = upgrade || views.len() < VIEW_NAMES.len();
        if views_due && !refused.is_empty() {
            return Err(StoreError {
                kind: StoreErrorKind::Permission,
                message: "the Recall views need columns this user may not add".to_owned(),
            });
        }
        for (name, statement) in view_statements(Dialect::ClickHouse, &self.location.options) {
            if upgrade {
                self.command(py, &statement, "create the Recall views")?;
            } else if !views.contains(name) {
                let statement =
                    statement.replacen("CREATE OR REPLACE VIEW", "CREATE VIEW IF NOT EXISTS", 1);
                self.command(py, &statement, "create the Recall views")?;
            }
        }
        if version < RECALL_SCHEMA_VERSION {
            self.record_version(py, envelope)?;
        }
        Ok(ReadyStore {
            tables,
            refused_columns: refused,
        })
    }

    /// Create every table, column and view of a store whose tables are missing.
    fn create(
        &mut self,
        py: Python<'_>,
        envelope: &RowEnvelope,
        views: &HashSet<String>,
    ) -> Result<(), StoreError> {
        self.require_database(py)?;
        for statement in table_statements(Dialect::ClickHouse, &self.location.options) {
            self.command(py, &statement, "create the Recall tables")?;
        }
        self.read_columns(py)?;
        let refused: Vec<String> = self.add_columns(py)?;
        if !refused.is_empty() {
            return Err(StoreError {
                kind: StoreErrorKind::Permission,
                message: "the Recall tables need columns this user may not add".to_owned(),
            });
        }
        for (name, statement) in view_statements(Dialect::ClickHouse, &self.location.options) {
            if !views.contains(name) {
                self.command(py, &statement, "create the Recall views")?;
            }
        }
        self.record_version(py, envelope)
    }

    /// Add the additive columns the stored tables lack; when the user may not, the statements an administrator must run.
    fn add_columns(&mut self, py: Python<'_>) -> Result<Vec<String>, StoreError> {
        let missing: Vec<(Table, ColumnSpec)> = self.missing_columns();
        let statements: Vec<String> = missing
            .iter()
            .map(|(table, column)| {
                add_column_statement(
                    Dialect::ClickHouse,
                    &self.location.options,
                    (table_spec(*table), column),
                )
            })
            .collect();
        for (index, statement) in statements.iter().enumerate() {
            match self.command(py, statement, "add a Recall column") {
                Ok(()) => {}
                Err(error) if error.kind == StoreErrorKind::Permission => {
                    return Ok(statements[index..].to_vec());
                }
                Err(error) => return Err(error),
            }
        }
        if !missing.is_empty() {
            self.read_columns(py)?;
        }
        Ok(Vec::new())
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

    /// The notice for columns this user may not add: history is written without them until an administrator adds them.
    fn columns_notice(&self, statements: &[String]) -> String {
        format!(
            "the ClickHouse store in `{}` lacks columns this version of SQLBuild writes, and this \
             user may not add them; history is still written without them. An administrator can \
             add them with:\n\n{};\n",
            self.location.database(),
            statements.join(";\n\n")
        )
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
                    (&self.location.config, true),
                    &self.location.connect_action(),
                )?),
                columns: HashMap::new(),
                notices: Vec::new(),
            };
            match store.ensure_schema(py, envelope) {
                Ok(ReadyStore {
                    tables,
                    refused_columns: refused,
                }) => {
                    if !refused.is_empty()
                        && (self.retention_notice)(
                            &self.project_dir,
                            &format!("{}:columns", self.location.database()),
                        )
                    {
                        store.notices.push(store.columns_notice(&refused));
                    }
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
                (&location.config, false),
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
        let location = &self.store.location;
        let started = format!(
            "(SELECT invocation_id, invocation_started_at FROM {} \
             UNION ALL SELECT invocation_id, invocation_started_at FROM {})",
            location.table(table_spec(Table::Invocations).name),
            location.table(table_spec(Table::Heartbeats).name),
        );
        let sql = if selector == LAST_INVOCATION_SELECTOR {
            format!(
                "SELECT invocation_id FROM {started} \
                 ORDER BY invocation_started_at DESC, invocation_id DESC LIMIT 1"
            )
        } else {
            format!(
                "SELECT DISTINCT invocation_id FROM {started} \
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
