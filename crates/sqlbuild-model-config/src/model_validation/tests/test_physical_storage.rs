use crate::model_validation::tests::helpers::{
    incremental, map, snapshot, strings, table, validation_outcome,
};
use crate::model_validation::tests::test_types::ValidateTestCase;
use crate::tests::test_types::Value;

#[test]
fn given_physical_layout_keys_when_validating_then_shapes_and_materializations_are_checked() {
    let test_cases = [
        ValidateTestCase {
            description: "a complete layout on a table",
            config: table(vec![
                ("engine", Value::Str("ReplacingMergeTree(updated_at)")),
                ("order_by", strings(&["customer_id", "toDate(ordered_at)"])),
                ("partition_by", Value::Str("toYYYYMM(ordered_at)")),
                ("primary_key", strings(&["customer_id"])),
                (
                    "table_settings",
                    map(vec![
                        ("index_granularity", Value::Int(4096)),
                        ("allow_nullable_key", Value::Bool(true)),
                    ]),
                ),
            ]),
            references: &[],
            query_sql: "select 1",
            expected_outcome: "accepted",
        },
        ValidateTestCase {
            description: "a single sorting expression on an incremental model",
            config: incremental(vec![("order_by", Value::Str("order_id"))]),
            references: &["ref:orders"],
            query_sql: "select 1",
            expected_outcome: "accepted",
        },
        ValidateTestCase {
            description: "layout on a view",
            config: vec![
                ("materialized", Value::Str("view")),
                ("partition_by", Value::Str("toYYYYMM(ordered_at)")),
            ],
            references: &[],
            query_sql: "select 1",
            expected_outcome: "model 'orders_daily': partition_by is only valid for table and incremental models",
        },
        ValidateTestCase {
            description: "layout on a snapshot",
            config: snapshot(vec![("order_by", Value::Str("customer_id"))]),
            references: &["ref:customers"],
            query_sql: "select 1",
            expected_outcome: "model 'orders_daily': order_by is only valid for table and incremental models",
        },
        ValidateTestCase {
            description: "a shared engine",
            config: table(vec![("engine", Value::Str("SharedMergeTree"))]),
            references: &[],
            query_sql: "select 1",
            expected_outcome: "accepted",
        },
        ValidateTestCase {
            description: "a shared replacing engine with arguments",
            config: table(vec![(
                "engine",
                Value::Str("SharedReplacingMergeTree(updated_at)"),
            )]),
            references: &[],
            query_sql: "select 1",
            expected_outcome: "accepted",
        },
        ValidateTestCase {
            description: "a replicated replacing engine",
            config: table(vec![(
                "engine",
                Value::Str("ReplicatedReplacingMergeTree(updated_at)"),
            )]),
            references: &[],
            query_sql: "select 1",
            expected_outcome: "model 'orders_daily': engine 'ReplicatedReplacingMergeTree(updated_at)' must be a non-replicated MergeTree-family table engine",
        },
        ValidateTestCase {
            description: "a shared engine outside the MergeTree family",
            config: table(vec![("engine", Value::Str("SharedSet"))]),
            references: &[],
            query_sql: "select 1",
            expected_outcome: "model 'orders_daily': engine 'SharedSet' must be a non-replicated MergeTree-family table engine",
        },
        ValidateTestCase {
            description: "a replicated engine",
            config: table(vec![(
                "engine",
                Value::Str("ReplicatedMergeTree('/tables/orders', '{replica}')"),
            )]),
            references: &[],
            query_sql: "select 1",
            expected_outcome: "model 'orders_daily': engine 'ReplicatedMergeTree('/tables/orders', '{replica}')' must be a non-replicated MergeTree-family table engine",
        },
        ValidateTestCase {
            description: "an engine outside the MergeTree family",
            config: table(vec![("engine", Value::Str("Log"))]),
            references: &[],
            query_sql: "select 1",
            expected_outcome: "model 'orders_daily': engine 'Log' must be a non-replicated MergeTree-family table engine",
        },
        ValidateTestCase {
            description: "a blank sorting expression",
            config: table(vec![("order_by", strings(&["customer_id", " "]))]),
            references: &[],
            query_sql: "select 1",
            expected_outcome: "model 'orders_daily': order_by must be a SQL expression string or a list of them",
        },
        ValidateTestCase {
            description: "a partition expression that is not a string",
            config: table(vec![("partition_by", Value::Int(3))]),
            references: &[],
            query_sql: "select 1",
            expected_outcome: "model 'orders_daily': partition_by must be a non-empty SQL expression string",
        },
        ValidateTestCase {
            description: "a primary key that is not a sorting prefix",
            config: table(vec![
                ("order_by", strings(&["customer_id", "ordered_at"])),
                ("primary_key", strings(&["ordered_at"])),
            ]),
            references: &[],
            query_sql: "select 1",
            expected_outcome: "model 'orders_daily': primary_key must be a prefix of order_by",
        },
        ValidateTestCase {
            description: "a primary key prefix of a single sorting tuple string",
            config: table(vec![
                ("order_by", Value::Str("customer_id, ordered_at")),
                ("primary_key", Value::Str("customer_id")),
            ]),
            references: &[],
            query_sql: "select 1",
            expected_outcome: "accepted",
        },
        ValidateTestCase {
            description: "a parenthesized sorting tuple with nested calls and quotes",
            config: table(vec![
                (
                    "order_by",
                    Value::Str(
                        "(customer_id, toStartOfInterval(ordered_at, INTERVAL 1 day), 'a,b')",
                    ),
                ),
                (
                    "primary_key",
                    Value::Str("(customer_id, toStartOfInterval(ordered_at, INTERVAL 1 day))"),
                ),
            ]),
            references: &[],
            query_sql: "select 1",
            expected_outcome: "accepted",
        },
        ValidateTestCase {
            description: "a primary key string that is not a sorting prefix",
            config: table(vec![
                ("order_by", Value::Str("(customer_id, ordered_at)")),
                ("primary_key", Value::Str("ordered_at")),
            ]),
            references: &[],
            query_sql: "select 1",
            expected_outcome: "model 'orders_daily': primary_key must be a prefix of order_by",
        },
        ValidateTestCase {
            description: "a setting with a list value",
            config: table(vec![(
                "table_settings",
                map(vec![("index_granularity", strings(&["8192"]))]),
            )]),
            references: &[],
            query_sql: "select 1",
            expected_outcome: "model 'orders_daily': table_settings must map setting names to strings, integers or booleans",
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
