use crate::lineage::tests::rich_helpers::rich_outcome;
use crate::lineage::tests::test_types::RichLineageTestCase;

/// Expected lines are the wheel's output for the same SQL and schema (Python's rich path).
#[test]
fn given_models_when_building_rich_lineage_then_matches_the_wheel_path() {
    let test_cases = [
        RichLineageTestCase {
            description: "joins, aggregation, cast, constant and expression columns",
            dialect: "generic",
            sql: "SELECT o.order_id, c.name AS customer_name, SUM(o.amount) AS total, \
                  CAST(o.amount AS BIGINT) AS amount_big, 1 AS one, o.amount + c.customer_id AS mix \
                  FROM __ref('orders') o JOIN __ref('customers') c ON o.customer_id = c.customer_id \
                  GROUP BY 1, 2",
            expected_status: "built",
            expected_lines: &[
                "order_id direct high unknown [model:orders.order_id]",
                "customer_name direct high unknown [model:customers.name]",
                "total aggregation high unknown [model:orders.amount]",
                "amount_big cast high unknown [model:orders.amount]",
                "one constant high non_null []",
                "mix expression high unknown [model:customers.customer_id model:orders.amount]",
            ],
            expected_has_star: false,
            expected_detail: None,
        },
        RichLineageTestCase {
            description: "a root star expands schema columns after explicit outputs",
            dialect: "generic",
            sql: "SELECT *, amount AS amt FROM __ref('orders')",
            expected_status: "built",
            expected_lines: &[
                "amt direct high unknown [model:orders.amount]",
                "order_id star medium unknown [model:orders.order_id]",
                "customer_id star medium unknown [model:orders.customer_id]",
                "amount star medium unknown [model:orders.amount]",
            ],
            expected_has_star: true,
            expected_detail: None,
        },
        RichLineageTestCase {
            description: "a CTE star over a join with a seed, under DuckDB",
            dialect: "duckdb",
            sql: "WITH t AS (SELECT o.*, r.label FROM __ref('orders') o \
                  LEFT JOIN __seed('regions') r ON o.customer_id = r.region_id) \
                  SELECT order_id, COALESCE(label, 'none') AS label, amount FROM t",
            expected_status: "built",
            expected_lines: &[
                "order_id direct high unknown [model:orders.order_id]",
                "label expression high non_null [seed:regions.label]",
                "amount direct high unknown [model:orders.amount]",
            ],
            expected_has_star: false,
            expected_detail: None,
        },
        RichLineageTestCase {
            description: "set operation branches merge sorted upstreams",
            dialect: "generic",
            sql: "SELECT customer_id, amount FROM __ref('orders') UNION ALL \
                  SELECT customer_id, 0 FROM __ref('customers')",
            expected_status: "built",
            expected_lines: &[
                "customer_id direct high unknown \
                 [model:customers.customer_id model:orders.customer_id]",
                "amount direct high unknown [model:orders.amount]",
            ],
            expected_has_star: false,
            expected_detail: None,
        },
        RichLineageTestCase {
            description: "an unknown qualifier and an unresolved column",
            dialect: "generic",
            sql: "SELECT missing.thing, order_id FROM __ref('orders') o \
                  JOIN __ref('customers') c ON TRUE",
            expected_status: "built",
            expected_lines: &[
                "thing constant high unknown []",
                "order_id constant unknown unknown []",
            ],
            expected_has_star: false,
            expected_detail: None,
        },
        RichLineageTestCase {
            description: "a resource without known columns",
            dialect: "generic",
            sql: "SELECT x FROM __source('unknown_feed')",
            expected_status: "built",
            expected_lines: &["x direct high unknown [source:unknown_feed.x]"],
            expected_has_star: false,
            expected_detail: None,
        },
        RichLineageTestCase {
            description: "a parse error skips the model with the wheel's message",
            dialect: "generic",
            sql: "SELECT FROM WHERE",
            expected_status: "skipped",
            expected_lines: &[],
            expected_has_star: false,
            expected_detail: Some(
                "Parse error at line 1, column 18: Expected table name or subquery, got Where",
            ),
        },
        RichLineageTestCase {
            description: "a dialect this build does not carry is deferred",
            dialect: "mysql",
            sql: "SELECT order_id FROM __ref('orders')",
            expected_status: "deferred",
            expected_lines: &[],
            expected_has_star: false,
            expected_detail: Some("unsupported_dialect"),
        },
    ];
    for test_case in test_cases {
        let (status, lines, has_star, detail) = rich_outcome(test_case.dialect, test_case.sql);
        assert_eq!(status, test_case.expected_status, "{}", test_case.description);
        assert_eq!(lines, test_case.expected_lines, "{}", test_case.description);
        assert_eq!(
            has_star, test_case.expected_has_star,
            "{}",
            test_case.description
        );
        assert_eq!(
            detail.as_deref(),
            test_case.expected_detail,
            "{}",
            test_case.description
        );
    }
}
