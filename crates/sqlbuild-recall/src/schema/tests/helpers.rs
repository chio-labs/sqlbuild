use crate::schema::constants::VIEW_NAMES;
use crate::schema::main::ddl_script::ddl_script;
use crate::schema::main::sqlite_retention_sql::sqlite_retention_sql;
use crate::schema::main::table_statements::table_statements;
use crate::schema::models::{DdlOptions, Dialect};

/// Options rendering into `observability` with 14-day retention, optionally on `cluster`.
pub(crate) fn options(cluster: Option<&str>) -> DdlOptions {
    DdlOptions {
        database: Some("observability".to_owned()),
        retention_days: 14,
        cluster: cluster.map(str::to_owned),
    }
}

/// The ClickHouse `CREATE TABLE` statement for `table`.
pub(crate) fn clickhouse_table(table: &str, cluster: Option<&str>) -> String {
    let quoted = format!("`{table}`");
    table_statements(Dialect::ClickHouse, &options(cluster))
        .into_iter()
        .find(|statement| statement.contains(&quoted))
        .unwrap_or_default()
}

/// The `fragments` that `statement` contains, in order.
pub(crate) fn contained<'a>(statement: &str, fragments: &[&'a str]) -> Vec<&'a str> {
    fragments
        .iter()
        .copied()
        .filter(|fragment| statement.contains(fragment))
        .collect()
}

/// Schema objects after running the SQLite script `runs` times, and the statements that fail.
pub(crate) fn sqlite_schema_after(runs: usize) -> (usize, Vec<String>) {
    let connection = rusqlite::Connection::open_in_memory().expect("an in-memory database opens");
    let script = ddl_script(Dialect::Sqlite, &options(None));
    let mut failures: Vec<String> = Vec::new();
    for run in 0..runs {
        let outcome: rusqlite::Result<()> = connection.execute_batch(&script);
        failures.extend(outcome.err().map(|error| format!("run {run}: {error}")));
    }
    let retention = sqlite_retention_sql();
    let mut statements: Vec<String> = VIEW_NAMES
        .iter()
        .map(|view| format!("SELECT * FROM \"{view}\""))
        .collect();
    statements.push(retention.expired_invocations.clone());
    statements.extend(
        retention
            .delete_invocations
            .iter()
            .map(|(_, delete)| delete.clone()),
    );
    statements.push(retention.delete_orphan_artifacts.clone());
    for statement in statements {
        let prepared: rusqlite::Result<rusqlite::Statement<'_>> = connection.prepare(&statement);
        failures.extend(prepared.err().map(|error| format!("{statement}: {error}")));
    }
    let count: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM sqlite_schema WHERE type IN ('table', 'view')",
            [],
            |row| row.get(0),
        )
        .expect("the count query runs");
    (usize::try_from(count).unwrap_or_default(), failures)
}
