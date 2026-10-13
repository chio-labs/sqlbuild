use crate::header_metadata::tests::helpers::{map, schema_column_summary};
use crate::header_metadata::tests::test_types::SchemaColumnsTestCase;
use crate::tests::test_types::Value;

#[test]
fn given_schema_columns_when_parsing_then_required_columns_and_model_only_keys_are_enforced() {
    let test_cases = [
        SchemaColumnsTestCase {
            description: "declared columns keep authored order",
            columns: map(&[("order_id", map(&[])), ("amount", map(&[]))]),
            expected_summary: "order_id,amount",
        },
        SchemaColumnsTestCase {
            description: "absent columns fail when columns are required",
            columns: Value::Null,
            expected_summary: "/project/schemas/orders.sql schema 'orders' must declare at least one column",
        },
        SchemaColumnsTestCase {
            description: "an empty mapping fails when columns are required",
            columns: Value::Map(Vec::new()),
            expected_summary: "/project/schemas/orders.sql schema 'orders' must declare at least one column",
        },
        SchemaColumnsTestCase {
            description: "migrate_from is a model-only key",
            columns: map(&[("order_id", map(&[("migrate_from", Value::Str("id"))]))]),
            expected_summary: "/project/schemas/orders.sql schema 'orders' column 'order_id' has unknown metadata keys: migrate_from",
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            schema_column_summary(&test_case.columns),
            test_case.expected_summary,
            "{}",
            test_case.description
        );
    }
}
