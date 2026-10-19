use crate::schema::constants::{ALL_TABLES, VIEW_NAMES};
use crate::schema::main::add_column_statement::add_column_statement;
use crate::schema::main::ddl_script::ddl_script;
use crate::schema::main::sqlite_retention_sql::sqlite_retention_sql;
use crate::schema::main::table_spec::table_spec;
use crate::schema::main::table_statements::table_statements;
use crate::schema::main::view_statements::view_statements;
use crate::schema::models::{ColumnSpec, ColumnType, DdlOptions, Dialect, Table};

fn options(cluster: Option<&str>) -> DdlOptions {
    DdlOptions {
        database: Some("observability".to_owned()),
        retention_days: 14,
        cluster: cluster.map(str::to_owned),
    }
}

#[test]
fn given_sqlite_script_when_run_twice_then_every_table_and_view_exists() {
    let connection = rusqlite::Connection::open_in_memory().expect("memory database");
    let script = ddl_script(Dialect::Sqlite, &options(None));
    connection.execute_batch(&script).expect("first run");
    connection
        .execute_batch(&script)
        .expect("rerun is idempotent");
    let count: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM sqlite_schema WHERE type IN ('table', 'view')",
            [],
            |row| row.get(0),
        )
        .expect("count");
    assert_eq!(count as usize, ALL_TABLES.len() + VIEW_NAMES.len());
    for view in VIEW_NAMES {
        connection
            .prepare(&format!("SELECT * FROM \"{view}\""))
            .unwrap_or_else(|error| panic!("{view}: {error}"));
    }
    let retention = sqlite_retention_sql();
    connection
        .prepare(&retention.expired_invocations)
        .expect("expired query prepares");
    for (_, delete) in &retention.delete_invocations {
        connection.prepare(delete).expect("delete prepares");
    }
    connection
        .prepare(&retention.delete_orphan_artifacts)
        .expect("artifact delete prepares");
}

#[test]
fn given_clickhouse_options_when_rendered_then_engines_ttl_and_partitions_follow_the_table() {
    let statements = table_statements(Dialect::ClickHouse, &options(None));
    assert_eq!(statements.len(), ALL_TABLES.len());
    let output = statements
        .iter()
        .find(|statement| statement.contains("`recall_output`"))
        .expect("output table");
    assert!(output.starts_with("CREATE TABLE IF NOT EXISTS `observability`.`recall_output` ("));
    assert!(output.contains("ENGINE = ReplacingMergeTree()"));
    assert!(
        statements
            .iter()
            .any(|statement| statement.contains("ENGINE = ReplacingMergeTree(seen_at)"))
    );
    assert!(output.contains("PARTITION BY toDate(invocation_started_at)"));
    assert!(output.contains("ORDER BY (invocation_id, sequence)"));
    assert!(output.contains("TTL invocation_started_at + INTERVAL 14 DAY"));
    assert!(output.contains("`data` String"));
    assert!(output.contains("`priority` Nullable(String)"));
    let artifacts = statements
        .iter()
        .find(|statement| statement.contains("`recall_artifacts`"))
        .expect("artifacts table");
    assert!(artifacts.contains("TTL seen_at + INTERVAL 21 DAY"));
    let heartbeats = statements
        .iter()
        .find(|statement| statement.contains("`recall_heartbeats`"))
        .expect("heartbeat table");
    assert!(heartbeats.contains("ENGINE = MergeTree()"));
}

#[test]
fn given_a_cluster_when_rendered_then_tables_are_replicated_on_cluster() {
    let statements = table_statements(Dialect::ClickHouse, &options(Some("analytics")));
    assert!(
        statements
            .iter()
            .all(|statement| statement.contains(" ON CLUSTER `analytics` ("))
    );
    assert!(statements[1].contains(
        "ReplicatedReplacingMergeTree('/clickhouse/tables/{uuid}/{shard}', '{replica}')"
    ));
    let views = view_statements(Dialect::ClickHouse, &options(Some("analytics")));
    assert_eq!(views.len(), VIEW_NAMES.len());
    assert!(views.iter().all(
        |(_, statement)| statement.starts_with("CREATE OR REPLACE VIEW")
            && statement.contains("ON CLUSTER `analytics`")
    ));
}

#[test]
fn given_clickhouse_views_when_rendered_then_rows_are_deduplicated_within_retention() {
    for (name, statement) in view_statements(Dialect::ClickHouse, &options(None)) {
        assert!(
            statement.contains("now64(6) - INTERVAL 14 DAY") && statement.contains("LIMIT 1 BY"),
            "{name} must deduplicate and filter by retention"
        );
    }
}

#[test]
fn given_a_new_column_when_upgraded_then_the_statement_is_additive_and_nullable() {
    let column = ColumnSpec {
        name: "new_field",
        column_type: ColumnType::Integer,
        nullable: false,
    };
    let spec = table_spec(Table::Events);
    assert_eq!(
        add_column_statement(Dialect::Sqlite, &options(None), (spec, &column)),
        "ALTER TABLE \"recall_events\" ADD COLUMN \"new_field\" INTEGER"
    );
    assert_eq!(
        add_column_statement(Dialect::ClickHouse, &options(None), (spec, &column)),
        "ALTER TABLE `observability`.`recall_events` ADD COLUMN IF NOT EXISTS `new_field` \
         Nullable(Int64)"
    );
}
