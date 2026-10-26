use crate::sql_macros::tests::helpers::expanded_for;
use crate::sql_macros::tests::test_types::{ExpansionErrorTestCase, ExpansionTestCase};

const WEEKLY_RATES: (&str, &str) = (
    "weekly_rates",
    "MACRO (\n  description \"Weekly order and refund rates per grain\",\n  arguments (weekly RELATION (keys COLUMNS, order_count BIGINT, refund_count BIGINT)),\n);\n\nWITH counted AS (\n  SELECT\n    s.@weekly.keys,\n    s.@weekly.order_count AS orders,\n    s.@weekly.refund_count AS refunds,\n    ROW_NUMBER() OVER (PARTITION BY s.@weekly.keys ORDER BY s.@weekly.order_count DESC) AS week_rank\n  FROM @weekly AS s\n),\nrated AS (\n  SELECT counted.@weekly.keys, SUM(refunds) / NULLIF(SUM(orders), 0) AS refund_rate\n  FROM counted\n  GROUP BY counted.@weekly.keys\n  ORDER BY counted.@weekly.keys\n)\n",
);
const RATE_COLUMNS: (&str, &str) = (
    "rate_columns",
    "MACRO (\n  description \"Grain and refund rate columns\",\n  arguments (weekly RELATION (keys COLUMNS, refund_rate DOUBLE)),\n);\n\nSELECT @weekly.keys, @weekly.refund_rate AS rate\n",
);
const ORDER_COUNTS: (&str, &str) = (
    "order_counts",
    "MACRO (\n  description \"Order counts\",\n  arguments (weekly RELATION (order_count BIGINT)),\n);\n\nSELECT @weekly.order_count\n",
);
const UNNAMED_COUNTS: (&str, &str) = (
    "unnamed_counts",
    "MACRO (\n  description \"Order counts plus one\",\n  arguments (weekly RELATION (order_count BIGINT)),\n);\n\nWITH bumped AS (SELECT @weekly.order_count + 1 FROM @weekly)\n",
);
const SCALED_COUNT: (&str, &str) = (
    "scaled_count",
    "MACRO (\n  description \"Scaled order count\",\n  arguments (weekly RELATION (order_count BIGINT), factor BIGINT),\n  returns BIGINT,\n);\n\n@weekly.order_count * @factor\n",
);
const CARRIED_TOTALS: (&str, &str) = (
    "carried_totals",
    "MACRO (\n  description \"Totals per grain, carrying extra columns\",\n  arguments (weekly RELATION (keys COLUMNS, carried COLUMNS, order_count BIGINT)),\n);\n\nWITH totals AS (\n  SELECT @weekly.keys, @weekly.carried, SUM(@weekly.order_count) AS total\n  FROM @weekly\n  GROUP BY @weekly.keys, @weekly.carried\n)\n",
);
const JOINED_RATES: (&str, &str) = (
    "joined_rates",
    "MACRO (\n  description \"Rates joined back on the grain\",\n  arguments (weekly RELATION (keys COLUMNS), rates RELATION (refund_rate DOUBLE)),\n);\n\nWITH joined AS (SELECT * FROM @weekly JOIN @rates USING (@weekly.keys))\n",
);
const FORWARDED_RATES: (&str, &str) = (
    "forwarded_rates",
    "MACRO (\n  description \"Weekly rates through another macro\",\n  arguments (src RELATION (dims COLUMNS, placed BIGINT, refunded BIGINT)),\n);\n\nWITH @sql.weekly_rates(weekly := @src, weekly.keys := (dims), weekly.order_count := placed, weekly.refund_count := refunded)\n",
);
const FORWARDED_SAME_NAME: (&str, &str) = (
    "forwarded_same_name",
    "MACRO (\n  description \"Weekly rates through another macro with the same relation name\",\n  arguments (weekly RELATION (dims COLUMNS, order_count BIGINT, refund_count BIGINT)),\n);\n\nWITH @sql.weekly_rates(weekly := @weekly, weekly.keys := (dims))\n",
);
const RATE_TOTAL: (&str, &str) = (
    "rate_total",
    "MACRO (\n  description \"Refund rate of one row\",\n  arguments (weekly RELATION (order_count BIGINT, refund_count BIGINT)),\n  returns DOUBLE,\n);\n\n@weekly.refund_count / NULLIF(@weekly.order_count, 0)\n",
);

#[test]
fn given_relation_slots_when_expanding_then_each_read_becomes_the_mapped_columns() {
    let test_cases = [
        ExpansionTestCase {
            description: "a COLUMNS slot at one grain matches the hand-written per-product SQL",
            adapter: "",
            macros: &[WEEKLY_RATES],
            sql: "WITH weekly_orders AS (SELECT 1 AS product_id, 2 AS orders_placed, 0 AS refund_count),\n@sql.weekly_rates(weekly := weekly_orders, weekly.keys := (product_id), weekly.order_count := orders_placed)\nSELECT * FROM rated",
            expected_sql: "WITH weekly_orders AS (SELECT 1 AS product_id, 2 AS orders_placed, 0 AS refund_count),\ncounted AS (\n  SELECT\n    s.product_id,\n    s.orders_placed AS orders,\n    s.refund_count AS refunds,\n    ROW_NUMBER() OVER (PARTITION BY s.product_id ORDER BY s.orders_placed DESC) AS week_rank\n  FROM weekly_orders AS s\n),\nrated AS (\n  SELECT counted.product_id, SUM(refunds) / NULLIF(SUM(orders), 0) AS refund_rate\n  FROM counted\n  GROUP BY counted.product_id\n  ORDER BY counted.product_id\n)\nSELECT * FROM rated",
        },
        ExpansionTestCase {
            description: "a COLUMNS slot at two columns prefixes every column with the alias",
            adapter: "",
            macros: &[WEEKLY_RATES],
            sql: "WITH weekly_orders AS (SELECT 1 AS product_id, 'EU' AS region, 2 AS order_count, 0 AS refund_count),\n@sql.weekly_rates(weekly := weekly_orders, weekly.keys := (product_id, region), __cte := by_region)\nSELECT * FROM by_region",
            expected_sql: "WITH weekly_orders AS (SELECT 1 AS product_id, 'EU' AS region, 2 AS order_count, 0 AS refund_count),\nby_region__counted AS (\n  SELECT\n    s.product_id, s.region,\n    s.order_count AS orders,\n    s.refund_count AS refunds,\n    ROW_NUMBER() OVER (PARTITION BY s.product_id, s.region ORDER BY s.order_count DESC) AS week_rank\n  FROM weekly_orders AS s\n),\nby_region AS (\n  SELECT by_region__counted.product_id, by_region__counted.region, SUM(refunds) / NULLIF(SUM(orders), 0) AS refund_rate\n  FROM by_region__counted\n  GROUP BY by_region__counted.product_id, by_region__counted.region\n  ORDER BY by_region__counted.product_id, by_region__counted.region\n)\nSELECT * FROM by_region",
        },
        ExpansionTestCase {
            description: "plain group reads of a reference relation stand bare, unmapped slot reads qualified",
            adapter: "",
            macros: &[CARRIED_TOTALS],
            sql: "WITH @sql.carried_totals(__ref(\"weekly_orders\"), weekly.keys := (product_id), weekly.carried := (region, channel)) SELECT * FROM totals",
            expected_sql: "WITH totals AS (\n  SELECT product_id, region, channel, SUM(weekly.order_count) AS total\n  FROM __ref(\"weekly_orders\") AS weekly\n  GROUP BY product_id, region, channel\n) SELECT * FROM totals",
        },
        ExpansionTestCase {
            description: "a COLUMNS slot in USING",
            adapter: "",
            macros: &[JOINED_RATES],
            sql: "WITH a AS (SELECT 1 AS product_id), b AS (SELECT 1 AS product_id, 0.5 AS refund_rate), @sql.joined_rates(a, b, weekly.keys := (product_id)) SELECT * FROM joined",
            expected_sql: "WITH a AS (SELECT 1 AS product_id), b AS (SELECT 1 AS product_id, 0.5 AS refund_rate), joined AS (SELECT * FROM a JOIN b USING (product_id)) SELECT * FROM joined",
        },
        ExpansionTestCase {
            description: "a column-list macro inserts a group's columns with their own names",
            adapter: "",
            macros: &[RATE_COLUMNS],
            sql: "SELECT w.week, @sql.rate_columns(w, weekly.keys := (product_id, region)) FROM weekly_rates AS w",
            expected_sql: "SELECT w.week, product_id, region, w.refund_rate AS rate FROM weekly_rates AS w",
        },
        ExpansionTestCase {
            description: "an unmapped single-column slot read keeps its own name, qualified by the relation",
            adapter: "",
            macros: &[ORDER_COUNTS],
            sql: "SELECT @sql.order_counts(w) FROM weekly_orders AS w",
            expected_sql: "SELECT w.order_count FROM weekly_orders AS w",
        },
        ExpansionTestCase {
            description: "a plain read of a mapped single slot reads its mapped column through the relation",
            adapter: "",
            macros: &[(
                "counted_regions",
                "MACRO (description \"Order counts and regions\", arguments (weekly RELATION (order_count BIGINT)));\n\nSELECT @weekly.order_count AS orders, @weekly.region",
            )],
            sql: "SELECT @sql.counted_regions(w, weekly.order_count := orders_placed) FROM weekly_orders AS w",
            expected_sql: "SELECT w.orders_placed AS orders, w.region FROM weekly_orders AS w",
        },
        ExpansionTestCase {
            description: "an expression macro reads mapped single-column slots",
            adapter: "",
            macros: &[RATE_TOTAL],
            sql: "SELECT @sql.rate_total(w, weekly.order_count := orders_placed) AS refund_rate FROM weekly_orders AS w",
            expected_sql: "SELECT w.refund_count / NULLIF(w.orders_placed, 0) AS refund_rate FROM weekly_orders AS w",
        },
        ExpansionTestCase {
            description: "a relation forwarded to another macro maps the inner slots through the outer ones",
            adapter: "",
            macros: &[WEEKLY_RATES, FORWARDED_RATES],
            sql: "WITH weekly_orders AS (SELECT 1 AS product_id, 2 AS placed_count, 0 AS refunded_count),\n@sql.forwarded_rates(weekly_orders, src.dims := (product_id), src.placed := placed_count, src.refunded := refunded_count)\nSELECT * FROM rated",
            expected_sql: "WITH weekly_orders AS (SELECT 1 AS product_id, 2 AS placed_count, 0 AS refunded_count),\ncounted AS (\n  SELECT\n    s.product_id,\n    s.placed_count AS orders,\n    s.refunded_count AS refunds,\n    ROW_NUMBER() OVER (PARTITION BY s.product_id ORDER BY s.placed_count DESC) AS week_rank\n  FROM weekly_orders AS s\n),\nrated AS (\n  SELECT counted.product_id, SUM(refunds) / NULLIF(SUM(orders), 0) AS refund_rate\n  FROM counted\n  GROUP BY counted.product_id\n  ORDER BY counted.product_id\n)\nSELECT * FROM rated",
        },
        ExpansionTestCase {
            description: "a relation forwarded under its own name maps the inner slots",
            adapter: "",
            macros: &[WEEKLY_RATES, FORWARDED_SAME_NAME],
            sql: "WITH weekly_orders AS (SELECT 1 AS product_id, 2 AS order_count, 0 AS refund_count),\n@sql.forwarded_same_name(weekly_orders, weekly.dims := (product_id))\nSELECT * FROM rated",
            expected_sql: "WITH weekly_orders AS (SELECT 1 AS product_id, 2 AS order_count, 0 AS refund_count),\ncounted AS (\n  SELECT\n    s.product_id,\n    s.order_count AS orders,\n    s.refund_count AS refunds,\n    ROW_NUMBER() OVER (PARTITION BY s.product_id ORDER BY s.order_count DESC) AS week_rank\n  FROM weekly_orders AS s\n),\nrated AS (\n  SELECT counted.product_id, SUM(refunds) / NULLIF(SUM(orders), 0) AS refund_rate\n  FROM counted\n  GROUP BY counted.product_id\n  ORDER BY counted.product_id\n)\nSELECT * FROM rated",
        },
    ];

    for test_case in test_cases {
        let expanded = expanded_for(test_case.adapter, test_case.macros, test_case.sql)
            .unwrap_or_else(|error| panic!("{}: {}", test_case.description, error.message));

        assert_eq!(
            expanded, test_case.expected_sql,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_wrong_slot_mappings_when_expanding_then_each_call_fails_with_its_message() {
    let test_cases = [
        ExpansionErrorTestCase {
            description: "an unmapped COLUMNS slot",
            adapter: "",
            macros: &[WEEKLY_RATES],
            sql: "WITH w AS (SELECT 1 AS product_id), @sql.weekly_rates(w) SELECT * FROM rated",
            expected_code: "P017",
            expected_message: "call to macro weekly_rates() is missing slot weekly.keys COLUMNS",
        },
        ExpansionErrorTestCase {
            description: "an empty COLUMNS slot",
            adapter: "",
            macros: &[WEEKLY_RATES],
            sql: "WITH w AS (SELECT 1 AS product_id), @sql.weekly_rates(w, weekly.keys := ()) SELECT * FROM rated",
            expected_code: "P017",
            expected_message: "slot weekly.keys of macro weekly_rates() needs at least one column; got ()",
        },
        ExpansionErrorTestCase {
            description: "a COLUMNS slot mapped without parentheses",
            adapter: "",
            macros: &[WEEKLY_RATES],
            sql: "WITH w AS (SELECT 1 AS product_id), @sql.weekly_rates(w, weekly.keys := product_id) SELECT * FROM rated",
            expected_code: "P017",
            expected_message: "slot weekly.keys of macro weekly_rates() takes a parenthesised list of column names of the passed relation; got product_id",
        },
        ExpansionErrorTestCase {
            description: "a COLUMNS slot mapped to an expression",
            adapter: "",
            macros: &[WEEKLY_RATES],
            sql: "WITH w AS (SELECT 1 AS product_id), @sql.weekly_rates(w, weekly.keys := (UPPER(region))) SELECT * FROM rated",
            expected_code: "P017",
            expected_message: "slot weekly.keys of macro weekly_rates() takes a parenthesised list of column names of the passed relation; got (UPPER(region))",
        },
        ExpansionErrorTestCase {
            description: "a column listed twice in one group",
            adapter: "",
            macros: &[WEEKLY_RATES],
            sql: "WITH w AS (SELECT 1 AS product_id), @sql.weekly_rates(w, weekly.keys := (product_id, PRODUCT_ID)) SELECT * FROM rated",
            expected_code: "P017",
            expected_message: "column PRODUCT_ID is listed twice in slot weekly.keys of macro weekly_rates()",
        },
        ExpansionErrorTestCase {
            description: "a single-column slot mapped to an expression",
            adapter: "",
            macros: &[WEEKLY_RATES],
            sql: "WITH w AS (SELECT 1 AS product_id), @sql.weekly_rates(w, weekly.keys := (product_id), weekly.order_count := orders + 1) SELECT * FROM rated",
            expected_code: "P017",
            expected_message: "slot weekly.order_count of macro weekly_rates() takes one column name of the passed relation; got orders + 1",
        },
        ExpansionErrorTestCase {
            description: "a slot the relation does not declare",
            adapter: "",
            macros: &[WEEKLY_RATES],
            sql: "WITH w AS (SELECT 1 AS product_id), @sql.weekly_rates(w, weekly.keys := (product_id), weekly.region := region) SELECT * FROM rated",
            expected_code: "P017",
            expected_message: "RELATION argument weekly of macro weekly_rates() has no slot region",
        },
        ExpansionErrorTestCase {
            description: "a slot of an argument the macro does not have",
            adapter: "",
            macros: &[RATE_TOTAL],
            sql: "SELECT @sql.rate_total(w, weekly.order_count := orders_placed, places.order_count := orders) AS r FROM weekly_orders AS w",
            expected_code: "P017",
            expected_message: "macro rate_total() has no argument places",
        },
        ExpansionErrorTestCase {
            description: "a slot mapped twice",
            adapter: "",
            macros: &[WEEKLY_RATES],
            sql: "WITH w AS (SELECT 1 AS product_id), @sql.weekly_rates(w, weekly.keys := (product_id), weekly.keys := (region)) SELECT * FROM rated",
            expected_code: "P017",
            expected_message: "slot weekly.keys of macro weekly_rates() is mapped twice",
        },
        ExpansionErrorTestCase {
            description: "overlapping groups of one relation",
            adapter: "",
            macros: &[CARRIED_TOTALS],
            sql: "WITH w AS (SELECT 1 AS product_id), @sql.carried_totals(w, weekly.keys := (product_id, region), weekly.carried := (region)) SELECT * FROM totals",
            expected_code: "P017",
            expected_message: "slots weekly.keys and weekly.carried of macro carried_totals() both group column region; groups of one relation may not overlap",
        },
        ExpansionErrorTestCase {
            description: "a grouped column that also fills a mapped single-column slot",
            adapter: "",
            macros: &[CARRIED_TOTALS],
            sql: "WITH w AS (SELECT 1 AS product_id), @sql.carried_totals(w, weekly.keys := (product_id), weekly.carried := (units), weekly.order_count := units) SELECT * FROM totals",
            expected_code: "P017",
            expected_message: "column units is in slot weekly.carried and also fills single-column slot weekly.order_count of macro carried_totals(); a grouped column may not fill a single-column slot",
        },
        ExpansionErrorTestCase {
            description: "a grouped column that an unmapped single-column slot reads by name",
            adapter: "",
            macros: &[CARRIED_TOTALS],
            sql: "WITH w AS (SELECT 1 AS product_id), @sql.carried_totals(w, weekly.keys := (product_id, order_count), weekly.carried := (region)) SELECT * FROM totals",
            expected_code: "P017",
            expected_message: "column order_count is in slot weekly.keys and also fills single-column slot weekly.order_count of macro carried_totals(); a grouped column may not fill a single-column slot",
        },
        ExpansionErrorTestCase {
            description: "a mapped single-column slot read in a select list without AS",
            adapter: "",
            macros: &[ORDER_COUNTS],
            sql: "SELECT @sql.order_counts(w, weekly.order_count := orders_placed) FROM weekly_orders AS w",
            expected_code: "P017",
            expected_message: "slot weekly.order_count of macro order_counts() is mapped to orders_placed, but the macro reads it in a select list without AS, so the output column's name would depend on the mapping",
        },
        ExpansionErrorTestCase {
            description: "a mapped single-column slot inside an unaliased select item",
            adapter: "",
            macros: &[UNNAMED_COUNTS],
            sql: "WITH w AS (SELECT 1 AS orders_placed), @sql.unnamed_counts(w, weekly.order_count := orders_placed) SELECT * FROM bumped",
            expected_code: "P017",
            expected_message: "slot weekly.order_count of macro unnamed_counts() is mapped to orders_placed, but the macro reads it in a select list without AS, so the output column's name would depend on the mapping",
        },
        ExpansionErrorTestCase {
            description: "a slot of an argument that is not a relation",
            adapter: "",
            macros: &[SCALED_COUNT],
            sql: "SELECT @sql.scaled_count(w, 2, factor.order_count := orders) AS r FROM weekly_orders AS w",
            expected_code: "P017",
            expected_message: "argument factor of macro scaled_count() is BIGINT, not a RELATION; only a RELATION argument has slots to map",
        },
        ExpansionErrorTestCase {
            description: "a grouped column that clashes with a column the macro defines",
            adapter: "",
            macros: &[WEEKLY_RATES],
            sql: "WITH w AS (SELECT 1 AS product_id), @sql.weekly_rates(w, weekly.keys := (product_id, refund_rate)) SELECT * FROM rated",
            expected_code: "P018",
            expected_message: "column refund_rate of slot weekly.keys clashes with column refund_rate that macro weekly_rates() defines",
        },
        ExpansionErrorTestCase {
            description: "a grouped column that clashes with a column of the caller's select list",
            adapter: "",
            macros: &[RATE_COLUMNS],
            sql: "SELECT w.region, @sql.rate_columns(w, weekly.keys := (product_id, region)) FROM weekly_rates AS w",
            expected_code: "P018",
            expected_message: "column \"region\" from macro rate_columns() clashes with a column already defined in model:orders_clean",
        },
        ExpansionErrorTestCase {
            description: "a positional argument after a slot mapping",
            adapter: "",
            macros: &[JOINED_RATES],
            sql: "WITH a AS (SELECT 1 AS product_id), @sql.joined_rates(a, weekly.keys := (product_id), b) SELECT * FROM joined",
            expected_code: "P017",
            expected_message: "positional argument after a named argument in a call to macro joined_rates()",
        },
    ];

    for test_case in test_cases {
        let error = expanded_for(test_case.adapter, test_case.macros, test_case.sql)
            .expect_err(test_case.description);

        assert_eq!(
            (error.code, error.message.as_str()),
            (test_case.expected_code, test_case.expected_message),
            "{}",
            test_case.description
        );
    }
}
