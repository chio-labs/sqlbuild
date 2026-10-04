use crate::compiler::tests::helpers::{
    owned_marker_calls, relation_marker_oracle_mismatches, relation_markers_and_json_oracle,
};
use crate::compiler::tests::test_types::{RelationMarkerOracleTestCase, RelationMarkersTestCase};

#[test]
fn given_parsed_statements_when_collecting_relation_markers_then_json_walk_order_is_reproduced() {
    let test_cases = [
        RelationMarkersTestCase {
            description: "plain reference",
            dialect: "duckdb",
            sql: "SELECT * FROM __ref(\"orders\")",
            expected_calls: &[("__ref", "orders")],
        },
        RelationMarkersTestCase {
            description: "aliased joins keep from before joins",
            dialect: "snowflake",
            sql: "SELECT o.id FROM __ref(\"orders\") AS o JOIN __source(\"raw_customers\") AS c ON o.id = c.id LEFT JOIN __seed(\"regions\") r ON c.region = r.id",
            expected_calls: &[
                ("__ref", "orders"),
                ("__source", "raw_customers"),
                ("__seed", "regions"),
            ],
        },
        RelationMarkersTestCase {
            description: "nested relations follow serialized field order",
            dialect: "duckdb",
            sql: "WITH recent AS (SELECT * FROM __ref(\"orders\")) SELECT (SELECT COUNT(*) FROM __ref(\"returns\")) AS returned FROM recent JOIN (SELECT * FROM __ref(\"customers\")) AS c ON TRUE WHERE EXISTS (SELECT 1 FROM __source(\"raw_events\"))",
            expected_calls: &[
                ("__ref", "returns"),
                ("__ref", "customers"),
                ("__source", "raw_events"),
                ("__ref", "orders"),
            ],
        },
        RelationMarkersTestCase {
            description: "dbt references with one and two arguments",
            dialect: "duckdb",
            sql: "SELECT * FROM __dbt_ref(\"orders\") JOIN __dbt_ref(\"shop\", \"customers\") ON TRUE",
            expected_calls: &[("__dbt_ref", "orders"), ("__dbt_ref", "shop__customers")],
        },
        RelationMarkersTestCase {
            description: "upper-case names are folded and unknown functions kept",
            dialect: "duckdb",
            sql: "SELECT * FROM __REF(\"Orders\") JOIN generate_rows(amount) ON TRUE",
            expected_calls: &[("__ref", "Orders"), ("generate_rows", "amount")],
        },
        RelationMarkersTestCase {
            description: "calls with several arguments or outside relations are ignored",
            dialect: "duckdb",
            sql: "SELECT __ref(\"orders\") AS value FROM __table_fn(\"orders\", 2) WHERE id IN (SELECT id FROM t)",
            expected_calls: &[],
        },
        RelationMarkersTestCase {
            description: "set operations walk each branch",
            dialect: "postgres",
            sql: "SELECT id FROM __ref(\"orders\") UNION ALL SELECT id FROM __ref(\"archived_orders\")",
            expected_calls: &[("__ref", "orders"), ("__ref", "archived_orders")],
        },
    ];
    for test_case in test_cases {
        let (collected, oracle) =
            relation_markers_and_json_oracle(test_case.dialect, test_case.sql);
        assert_eq!(
            collected,
            owned_marker_calls(test_case.expected_calls),
            "{}",
            test_case.description
        );
        assert_eq!(
            oracle,
            owned_marker_calls(test_case.expected_calls),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_generated_relation_shapes_when_collecting_markers_then_json_oracle_matches() {
    let test_cases = [
        RelationMarkerOracleTestCase {
            description: "duckdb relation shapes",
            dialect: "duckdb",
            expected_mismatches: &[],
        },
        RelationMarkerOracleTestCase {
            description: "snowflake relation shapes",
            dialect: "snowflake",
            expected_mismatches: &[],
        },
        RelationMarkerOracleTestCase {
            description: "postgres relation shapes",
            dialect: "postgres",
            expected_mismatches: &[],
        },
        RelationMarkerOracleTestCase {
            description: "bigquery relation shapes",
            dialect: "bigquery",
            expected_mismatches: &[],
        },
        RelationMarkerOracleTestCase {
            description: "tsql relation shapes",
            dialect: "tsql",
            expected_mismatches: &[],
        },
        RelationMarkerOracleTestCase {
            description: "databricks relation shapes",
            dialect: "databricks",
            expected_mismatches: &[],
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            relation_marker_oracle_mismatches(test_case.dialect),
            test_case.expected_mismatches,
            "{}",
            test_case.description
        );
    }
}
