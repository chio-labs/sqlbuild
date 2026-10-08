use crate::model_validation::tests::helpers::{
    incremental, map, snapshot, strings, validation_outcome,
};
use crate::model_validation::tests::test_types::ValidateTestCase;
use crate::tests::test_types::Value;

#[test]
fn given_effective_configs_when_validating_natively_then_python_outcomes_result() {
    let test_cases = [
        ValidateTestCase {
            description: "a plain table with known references",
            config: vec![("materialized", Value::Str("table"))],
            references: &[
                "ref:orders",
                "seed:regions",
                "source:raw.orders",
                "udf:cents",
            ],
            query_sql: "select 1",
            expected_outcome: "accepted",
        },
        ValidateTestCase {
            description: "an unknown model reference",
            config: vec![("materialized", Value::Str("table"))],
            references: &["ref:invoices"],
            query_sql: "select 1",
            expected_outcome: "Model file models/marts/orders_daily.sql references unknown model 'invoices'",
        },
        ValidateTestCase {
            description: "a table function called as a scalar function",
            config: vec![],
            references: &["udf:order_lines"],
            query_sql: "select 1",
            expected_outcome: "Model file models/marts/orders_daily.sql references table function 'order_lines' with __udf(); use __table_fn() in SQL contexts that support table-valued functions",
        },
        ValidateTestCase {
            description: "a dbt reference always defers to Python",
            config: vec![],
            references: &["dbt_ref:orders"],
            query_sql: "select 1",
            expected_outcome: "deferred",
        },
        ValidateTestCase {
            description: "an append incremental with ordered ISO bounds",
            config: incremental(vec![
                ("cursor_start", Value::Str("2024-01-01")),
                ("cursor_end", Value::Str("2024-02-01T00:00:00+00:00")),
                ("append_cursor_inclusive", Value::Bool(true)),
            ]),
            references: &["ref:orders"],
            query_sql: "select 1",
            expected_outcome: "accepted",
        },
        ValidateTestCase {
            description: "cursor bounds out of order",
            config: incremental(vec![
                ("cursor_start", Value::Str("2024-02-01")),
                ("cursor_end", Value::Str("2024-01-01")),
            ]),
            references: &["ref:orders"],
            query_sql: "select 1",
            expected_outcome: "model 'orders_daily': cursor_start must be before exclusive cursor_end",
        },
        ValidateTestCase {
            description: "a start bound shifted before year 1 in UTC fails",
            config: incremental(vec![
                ("cursor_start", Value::Str("0001-01-01T00:00:00+01:00")),
                ("cursor_end", Value::Str("2024-01-01")),
            ]),
            references: &["ref:orders"],
            query_sql: "select 1",
            expected_outcome: "model 'orders_daily': cursor_start value '0001-01-01T00:00:00+01:00' falls outside years 1-9999 once converted to UTC",
        },
        ValidateTestCase {
            description: "an end bound shifted past year 9999 in UTC fails",
            config: incremental(vec![
                ("cursor_start", Value::Str("2024-01-01")),
                ("cursor_end", Value::Str("9999-12-31T23:59:00-01:00")),
            ]),
            references: &["ref:orders"],
            query_sql: "select 1",
            expected_outcome: "model 'orders_daily': cursor_end value '9999-12-31T23:59:00-01:00' falls outside years 1-9999 once converted to UTC",
        },
        ValidateTestCase {
            description: "bounds at the edges of years 1 and 9999 in UTC",
            config: incremental(vec![
                ("cursor_start", Value::Str("0001-01-01T01:00:00+01:00")),
                ("cursor_end", Value::Str("9999-12-31T22:59:00-01:00")),
            ]),
            references: &["ref:orders"],
            query_sql: "select 1",
            expected_outcome: "accepted",
        },
        ValidateTestCase {
            description: "an unusual ISO timestamp defers",
            config: incremental(vec![("cursor_start", Value::Str("2024-W01-1"))]),
            references: &["ref:orders"],
            query_sql: "select 1",
            expected_outcome: "deferred",
        },
        ValidateTestCase {
            description: "a timestamp cursor without a grain",
            config: vec![
                ("materialized", Value::Str("incremental")),
                ("incremental_strategy", Value::Str("append")),
                ("cursor", Value::Str("updated_at")),
                ("cursor_type", Value::Str("timestamp")),
            ],
            references: &["ref:orders"],
            query_sql: "select 1",
            expected_outcome: "model 'orders_daily': cursor_type=timestamp requires cursor_grain (valid values: day, hour, minute, month, second, year)",
        },
        ValidateTestCase {
            description: "a watermark microbatch with a satisfiable limit",
            config: incremental(vec![
                ("incremental_strategy", Value::Str("delete_insert")),
                ("incremental_mode", Value::Str("microbatch")),
                ("microbatch_strategy", Value::Str("watermark")),
                ("cursor_watermark_mode", Value::Str("all")),
                ("batch_size", Value::Str("1d")),
                ("lookback", Value::Str("3d")),
                (
                    "cursor_inputs",
                    map(vec![(
                        "orders",
                        map(vec![
                            ("column", Value::Str("updated_at")),
                            ("roles", strings(&["filter", "watermark"])),
                        ]),
                    )]),
                ),
                (
                    "microbatch_limit",
                    map(vec![
                        ("max_batches", Value::Int(5)),
                        ("action", Value::Str("cap_from_start")),
                    ]),
                ),
            ]),
            references: &["ref:orders"],
            query_sql: "select 1",
            expected_outcome: "accepted",
        },
        ValidateTestCase {
            description: "a watermark limit below the lookback requirement",
            config: incremental(vec![
                ("incremental_strategy", Value::Str("delete_insert")),
                ("incremental_mode", Value::Str("microbatch")),
                ("microbatch_strategy", Value::Str("watermark")),
                ("cursor_watermark_mode", Value::Str("all")),
                ("batch_size", Value::Str("1d")),
                ("lookback", Value::Str("3d")),
                (
                    "cursor_inputs",
                    map(vec![(
                        "orders",
                        map(vec![
                            ("column", Value::Str("updated_at")),
                            ("roles", strings(&["watermark"])),
                        ]),
                    )]),
                ),
                ("max_microbatches", Value::Int(3)),
            ]),
            references: &["ref:orders"],
            query_sql: "select 1",
            expected_outcome: "model 'orders_daily': max_microbatches 3 is below the ordinary lookback requirement of 4 batches",
        },
        ValidateTestCase {
            description: "merge exclusions overlapping the unique key",
            config: incremental(vec![
                ("incremental_strategy", Value::Str("merge")),
                ("unique_key", Value::Str("Order_Id")),
                ("merge_exclude_columns", strings(&["order_id"])),
            ]),
            references: &["ref:orders"],
            query_sql: "select 1",
            expected_outcome: "model 'orders_daily': merge_exclude_columns cannot include unique_key column(s): order_id",
        },
        ValidateTestCase {
            description: "a bounded replay policy",
            config: incremental(vec![("replay_on_change", Value::Str("bounded- 14d"))]),
            references: &["ref:orders"],
            query_sql: "select 1",
            expected_outcome: "accepted",
        },
        ValidateTestCase {
            description: "an incremental-only key on a table",
            config: vec![
                ("materialized", Value::Str("table")),
                ("full_refresh", Value::Bool(true)),
            ],
            references: &[],
            query_sql: "select 1",
            expected_outcome: "model 'orders_daily': full_refresh is only valid for incremental models",
        },
        ValidateTestCase {
            description: "a timestamp snapshot with observed history",
            config: snapshot(vec![
                ("observed_at", Value::Str("loaded_at")),
                ("historical_input", Value::Str("snapshot")),
                ("invalidate_hard_deletes", Value::Bool(true)),
            ]),
            references: &["ref:orders"],
            query_sql: "select 1",
            expected_outcome: "accepted",
        },
        ValidateTestCase {
            description: "a check snapshot mixing the wildcard",
            config: snapshot(vec![
                ("snapshot_strategy", Value::Str("check")),
                ("check_columns", strings(&["*", "status"])),
            ]),
            references: &["ref:orders"],
            query_sql: "select 1",
            expected_outcome: "model 'orders_daily': check_columns [*] cannot be combined with explicit columns",
        },
        ValidateTestCase {
            description: "an enforced contract naming an undeclared unique key",
            config: snapshot(vec![
                ("contract", Value::Str("enforced")),
                ("columns", map(vec![("updated_at", Value::Null)])),
            ]),
            references: &["ref:orders"],
            query_sql: "select 1",
            expected_outcome: "model 'orders_daily': unique_key references column 'order_id' not declared in enforced contract",
        },
        ValidateTestCase {
            description: "a custom materialization with matching placeholders",
            config: vec![
                ("materialized", Value::Str("ledger")),
                ("placeholders", map(vec![("region", Value::Str("emea"))])),
            ],
            references: &[],
            query_sql: "select @@@region, '@@@' as marker",
            expected_outcome: "accepted",
        },
        ValidateTestCase {
            description: "placeholders on a built-in materialization",
            config: vec![("materialized", Value::Str("view"))],
            references: &[],
            query_sql: "select @@@region",
            expected_outcome: "model 'orders_daily': @@@placeholders are only allowed on custom materializations",
        },
        ValidateTestCase {
            description: "an unknown custom materialization",
            config: vec![("materialized", Value::Str("archive"))],
            references: &[],
            query_sql: "select 1",
            expected_outcome: "model 'orders_daily': unknown materialization 'archive'; not a built-in type and no custom materialization with that name was discovered",
        },
        ValidateTestCase {
            description: "a table migrating from an old name with an old-name view",
            config: vec![
                ("materialized", Value::Str("table")),
                ("migrate_from", Value::Str(" legacy_orders ")),
                ("old_name_view", Value::Str("7d")),
            ],
            references: &[],
            query_sql: "select 1",
            expected_outcome: "accepted",
        },
        ValidateTestCase {
            description: "a view forcing a migration",
            config: vec![
                ("materialized", Value::Str("view")),
                ("migrate_from", Value::Str("legacy_orders")),
                ("migrate_force", Value::Bool(true)),
            ],
            references: &[],
            query_sql: "select 1",
            expected_outcome: "model 'orders_daily': migrate_force is only valid for incremental and snapshot models; nothing is replaced when a 'view' model migrates, because tables and views are rebuilt under their new name",
        },
        ValidateTestCase {
            description: "an old-name view without a duration",
            config: vec![("old_name_view", Value::Null)],
            references: &[],
            query_sql: "select 1",
            expected_outcome: "model 'orders_daily': old_name_view must be a positive duration such as 7d, or false; got None",
        },
        ValidateTestCase {
            description: "concurrent batches without the project capability",
            config: incremental(vec![("batch_concurrency", Value::Int(2))]),
            references: &["ref:orders"],
            query_sql: "select 1",
            expected_outcome: "model 'orders_daily': batch_concurrency > 1 requires incremental_mode=microbatch",
        },
    ];

    for test_case in test_cases {
        let outcome =
            validation_outcome(test_case.config, test_case.references, test_case.query_sql);

        assert_eq!(
            outcome, test_case.expected_outcome,
            "{}",
            test_case.description
        );
    }
}
