use crate::model_validation::main::accept_model_config::accept_model_config;
use crate::model_validation::models::{ModelReference, ModelValidationFacts};
use crate::model_validation::tests::helpers::{incremental, map, project, snapshot, strings};
use crate::model_validation::tests::test_types::AcceptTestCase;
use crate::tests::test_types::Value;

#[test]
fn given_effective_configs_when_validating_natively_then_only_python_valid_configs_pass() {
    let test_cases = [
        AcceptTestCase {
            description: "a plain table with known references",
            config: vec![("materialized", Value::Str("table"))],
            references: &[
                "ref:orders",
                "seed:regions",
                "source:raw.orders",
                "udf:cents",
            ],
            query_sql: "select 1",
            expected_accepted: true,
        },
        AcceptTestCase {
            description: "an unknown model reference",
            config: vec![("materialized", Value::Str("table"))],
            references: &["ref:invoices"],
            query_sql: "select 1",
            expected_accepted: false,
        },
        AcceptTestCase {
            description: "a table function called as a scalar function",
            config: vec![],
            references: &["udf:order_lines"],
            query_sql: "select 1",
            expected_accepted: false,
        },
        AcceptTestCase {
            description: "a dbt reference always defers to Python",
            config: vec![],
            references: &["dbt_ref:orders"],
            query_sql: "select 1",
            expected_accepted: false,
        },
        AcceptTestCase {
            description: "an append incremental with ordered ISO bounds",
            config: incremental(vec![
                ("cursor_start", Value::Str("2024-01-01")),
                ("cursor_end", Value::Str("2024-02-01T00:00:00+00:00")),
                ("append_cursor_inclusive", Value::Bool(true)),
            ]),
            references: &["ref:orders"],
            query_sql: "select 1",
            expected_accepted: true,
        },
        AcceptTestCase {
            description: "cursor bounds out of order",
            config: incremental(vec![
                ("cursor_start", Value::Str("2024-02-01")),
                ("cursor_end", Value::Str("2024-01-01")),
            ]),
            references: &["ref:orders"],
            query_sql: "select 1",
            expected_accepted: false,
        },
        AcceptTestCase {
            description: "an unusual ISO timestamp defers",
            config: incremental(vec![("cursor_start", Value::Str("2024-W01-1"))]),
            references: &["ref:orders"],
            query_sql: "select 1",
            expected_accepted: false,
        },
        AcceptTestCase {
            description: "a timestamp cursor without a grain",
            config: vec![
                ("materialized", Value::Str("incremental")),
                ("incremental_strategy", Value::Str("append")),
                ("cursor", Value::Str("updated_at")),
                ("cursor_type", Value::Str("timestamp")),
            ],
            references: &["ref:orders"],
            query_sql: "select 1",
            expected_accepted: false,
        },
        AcceptTestCase {
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
            expected_accepted: true,
        },
        AcceptTestCase {
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
            expected_accepted: false,
        },
        AcceptTestCase {
            description: "merge exclusions overlapping the unique key",
            config: incremental(vec![
                ("incremental_strategy", Value::Str("merge")),
                ("unique_key", Value::Str("Order_Id")),
                ("merge_exclude_columns", strings(&["order_id"])),
            ]),
            references: &["ref:orders"],
            query_sql: "select 1",
            expected_accepted: false,
        },
        AcceptTestCase {
            description: "a bounded replay policy",
            config: incremental(vec![("replay_on_change", Value::Str("bounded- 14d"))]),
            references: &["ref:orders"],
            query_sql: "select 1",
            expected_accepted: true,
        },
        AcceptTestCase {
            description: "an incremental-only key on a table",
            config: vec![
                ("materialized", Value::Str("table")),
                ("full_refresh", Value::Bool(true)),
            ],
            references: &[],
            query_sql: "select 1",
            expected_accepted: false,
        },
        AcceptTestCase {
            description: "a timestamp snapshot with observed history",
            config: snapshot(vec![
                ("observed_at", Value::Str("loaded_at")),
                ("historical_input", Value::Str("snapshot")),
                ("invalidate_hard_deletes", Value::Bool(true)),
            ]),
            references: &["ref:orders"],
            query_sql: "select 1",
            expected_accepted: true,
        },
        AcceptTestCase {
            description: "a check snapshot mixing the wildcard",
            config: snapshot(vec![
                ("snapshot_strategy", Value::Str("check")),
                ("check_columns", strings(&["*", "status"])),
            ]),
            references: &["ref:orders"],
            query_sql: "select 1",
            expected_accepted: false,
        },
        AcceptTestCase {
            description: "an enforced contract naming an undeclared unique key",
            config: snapshot(vec![
                ("contract", Value::Str("enforced")),
                ("columns", map(vec![("updated_at", Value::Null)])),
            ]),
            references: &["ref:orders"],
            query_sql: "select 1",
            expected_accepted: false,
        },
        AcceptTestCase {
            description: "a custom materialization with matching placeholders",
            config: vec![
                ("materialized", Value::Str("ledger")),
                ("placeholders", map(vec![("region", Value::Str("emea"))])),
            ],
            references: &[],
            query_sql: "select @@@region, '@@@' as marker",
            expected_accepted: true,
        },
        AcceptTestCase {
            description: "placeholders on a built-in materialization",
            config: vec![("materialized", Value::Str("view"))],
            references: &[],
            query_sql: "select @@@region",
            expected_accepted: false,
        },
        AcceptTestCase {
            description: "an unknown custom materialization",
            config: vec![("materialized", Value::Str("archive"))],
            references: &[],
            query_sql: "select 1",
            expected_accepted: false,
        },
        AcceptTestCase {
            description: "a table migrating from an old name with an old-name view",
            config: vec![
                ("materialized", Value::Str("table")),
                ("migrate_from", Value::Str(" legacy_orders ")),
                ("old_name_view", Value::Str("7d")),
            ],
            references: &[],
            query_sql: "select 1",
            expected_accepted: true,
        },
        AcceptTestCase {
            description: "a view forcing a migration",
            config: vec![
                ("materialized", Value::Str("view")),
                ("migrate_from", Value::Str("legacy_orders")),
                ("migrate_force", Value::Bool(true)),
            ],
            references: &[],
            query_sql: "select 1",
            expected_accepted: false,
        },
        AcceptTestCase {
            description: "an old-name view without a duration",
            config: vec![("old_name_view", Value::Null)],
            references: &[],
            query_sql: "select 1",
            expected_accepted: false,
        },
        AcceptTestCase {
            description: "concurrent batches without the project capability",
            config: incremental(vec![("batch_concurrency", Value::Int(2))]),
            references: &["ref:orders"],
            query_sql: "select 1",
            expected_accepted: false,
        },
    ];

    for test_case in test_cases {
        let references: Vec<ModelReference> = test_case
            .references
            .iter()
            .filter_map(|reference| reference.split_once(':'))
            .map(|(kind, name)| ModelReference {
                kind: kind.to_owned(),
                name: name.to_owned(),
            })
            .collect();
        let facts = ModelValidationFacts {
            model_name: "orders_daily",
            references: &references,
            declared_columns: None,
            query_sql: test_case.query_sql,
            retention_unmanaged: true,
            table_type_declared: false,
        };
        let entries = test_case
            .config
            .into_iter()
            .map(|(key, value)| (Value::Str(key), value))
            .collect();

        let accepted = accept_model_config(entries, &project(), &facts) == Ok(());

        assert_eq!(
            accepted, test_case.expected_accepted,
            "{}",
            test_case.description
        );
    }
}
