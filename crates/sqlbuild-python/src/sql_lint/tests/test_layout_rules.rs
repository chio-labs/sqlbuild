use serde_json::Value;

use crate::sql_lint::tests::helpers::format_at_width;
use crate::sql_lint::tests::test_types;
use crate::sql_tokens::main::query_fingerprint::query_fingerprint;

#[test]
fn given_clause_layout_rules_when_formatting_then_each_rule_applies_idempotently()
-> Result<(), String> {
    let test_cases = [
        test_types::LayoutRuleTestCase {
            description: "a long Snowflake FROM VALUES puts each unsplit row on its own line",
            dialect: "snowflake",
            sql: "SELECT * FROM VALUES (1, '2024-01-15', 'PAID', 'north warehouse', 'priority shipping'), (2, '2024-01-16', 'OPEN', 'south warehouse', 'standard shipping')",
            line_width: 60,
            expected_sql: "SELECT *\nFROM VALUES\n  (1, '2024-01-15', 'PAID', 'north warehouse', 'priority shipping'),\n  (2, '2024-01-16', 'OPEN', 'south warehouse', 'standard shipping')",
        },
        test_types::LayoutRuleTestCase {
            description: "a short VALUES list stays on one line",
            dialect: "snowflake",
            sql: "SELECT * FROM VALUES ('a', 'A'), ('b', 'B')",
            line_width: 100,
            expected_sql: "SELECT *\nFROM VALUES ('a', 'A'), ('b', 'B')",
        },
        test_types::LayoutRuleTestCase {
            description: "a long parenthesized PostgreSQL VALUES moves under its parenthesis",
            dialect: "postgres",
            sql: "SELECT order_id, status FROM (VALUES (1, 'paid and shipped to customer'), (2, 'cancelled by customer')) AS orders(order_id, status)",
            line_width: 60,
            expected_sql: "SELECT\n  order_id,\n  status\nFROM (\n  VALUES\n    (1, 'paid and shipped to customer'),\n    (2, 'cancelled by customer')\n) AS orders(order_id, status)",
        },
        test_types::LayoutRuleTestCase {
            description: "a long T-SQL VALUES relation keeps rows whole",
            dialect: "tsql",
            sql: "SELECT order_id FROM (VALUES (1, 'paid and shipped to customer'), (2, 'cancelled by customer')) AS orders(order_id, status)",
            line_width: 60,
            expected_sql: "SELECT order_id\nFROM (\n  VALUES\n    (1, 'paid and shipped to customer'),\n    (2, 'cancelled by customer')\n) AS orders(order_id, status)",
        },
        test_types::LayoutRuleTestCase {
            description: "DuckDB INSERT VALUES rows stay whole when a row is over the width",
            dialect: "duckdb",
            sql: "INSERT INTO orders VALUES (1, 'paid and shipped to the customer by priority courier'), (2, 'open')",
            line_width: 40,
            expected_sql: "INSERT INTO orders\nVALUES\n  (1, 'paid and shipped to the customer by priority courier'),\n  (2, 'open')",
        },
        test_types::LayoutRuleTestCase {
            description: "Snowflake CAST breaks around IFF, not inside NUMBER(38, 2)",
            dialect: "snowflake",
            sql: "SELECT CAST(IFF(amount > 100000000, amount * 1000000000000, amount / 100000000000000) AS NUMBER(38, 2)) AS total FROM orders",
            line_width: 80,
            expected_sql: "SELECT\n  CAST(\n    IFF(\n      amount > 100000000,\n      amount * 1000000000000,\n      amount / 100000000000000\n    ) AS NUMBER(38, 2)\n  ) AS total\nFROM orders",
        },
        test_types::LayoutRuleTestCase {
            description: "a DuckDB :: cast keeps DECIMAL(18, 4) whole",
            dialect: "duckdb",
            sql: "SELECT COALESCE(first_order_amount, second_order_amount)::DECIMAL(18, 4) AS amount FROM orders",
            line_width: 50,
            expected_sql: "SELECT\n  COALESCE(\n    first_order_amount,\n    second_order_amount\n  )::DECIMAL(18, 4) AS amount\nFROM orders",
        },
        test_types::LayoutRuleTestCase {
            description: "a BigQuery NUMERIC(38, 9) cast keeps its parameters",
            dialect: "bigquery",
            sql: "SELECT CAST(COALESCE(first_order_amount, second_order_amount) AS NUMERIC(38, 9)) AS amount FROM orders",
            line_width: 50,
            expected_sql: "SELECT\n  CAST(\n    COALESCE(\n      first_order_amount,\n      second_order_amount\n    ) AS NUMERIC(38, 9)\n  ) AS amount\nFROM orders",
        },
        test_types::LayoutRuleTestCase {
            description: "a T-SQL VARCHAR(MAX) cast keeps its parameter",
            dialect: "tsql",
            sql: "SELECT CAST(COALESCE(first_order_note, second_order_note) AS VARCHAR(MAX)) AS note FROM orders",
            line_width: 50,
            expected_sql: "SELECT\n  CAST(\n    COALESCE(\n      first_order_note,\n      second_order_note\n    ) AS VARCHAR(MAX)\n  ) AS note\nFROM orders",
        },
        test_types::LayoutRuleTestCase {
            description: "a Databricks DECIMAL(10, 2) cast keeps its parameters",
            dialect: "databricks",
            sql: "SELECT CAST(COALESCE(first_order_amount, second_order_amount) AS DECIMAL(10, 2)) AS amount FROM orders",
            line_width: 50,
            expected_sql: "SELECT\n  CAST(\n    COALESCE(\n      first_order_amount,\n      second_order_amount\n    ) AS DECIMAL(10, 2)\n  ) AS amount\nFROM orders",
        },
        test_types::LayoutRuleTestCase {
            description: "a long Snowflake DECODE puts each pair and the default on its own line",
            dialect: "snowflake",
            sql: "SELECT DECODE(status, 1, 'new', 2, 'open', 3, 'paid', 4, 'shipped', 5, 'cancelled', 'unknown') AS status_name FROM orders",
            line_width: 60,
            expected_sql: "SELECT\n  DECODE(\n    status,\n    1, 'new',\n    2, 'open',\n    3, 'paid',\n    4, 'shipped',\n    5, 'cancelled',\n    'unknown'\n  ) AS status_name\nFROM orders",
        },
        test_types::LayoutRuleTestCase {
            description: "a DECODE without a default ends with a pair",
            dialect: "snowflake",
            sql: "SELECT DECODE(status, 1, 'new', 2, 'open', 3, 'paid', 4, 'shipped', 5, 'cancelled') AS status_name FROM orders",
            line_width: 60,
            expected_sql: "SELECT\n  DECODE(\n    status,\n    1, 'new',\n    2, 'open',\n    3, 'paid',\n    4, 'shipped',\n    5, 'cancelled'\n  ) AS status_name\nFROM orders",
        },
        test_types::LayoutRuleTestCase {
            description: "a DECODE the layout guide breaks is regrouped into pairs",
            dialect: "snowflake",
            sql: "SELECT DECODE(status, 1, 'new', 2, 'open', 3, 'paid', 4, 'shipped', 5, 'cancelled', 6, 'returned', 'unknown') AS status_name FROM orders",
            line_width: 100,
            expected_sql: "SELECT\n  DECODE(\n    status,\n    1, 'new',\n    2, 'open',\n    3, 'paid',\n    4, 'shipped',\n    5, 'cancelled',\n    6, 'returned',\n    'unknown'\n  ) AS status_name\nFROM orders",
        },
        test_types::LayoutRuleTestCase {
            description: "a short DECODE stays on one line",
            dialect: "snowflake",
            sql: "SELECT DECODE(status, 1, 'new', 'other') AS status_name FROM orders",
            line_width: 100,
            expected_sql: "SELECT DECODE(status, 1, 'new', 'other') AS status_name\nFROM orders",
        },
        test_types::LayoutRuleTestCase {
            description: "an operator after a multi-line CASE starts the next line",
            dialect: "duckdb",
            sql: "SELECT CASE WHEN status = 'paid' THEN 'customer paid in full' WHEN status = 'open' THEN 'customer has not paid yet' ELSE 'other' END || CASE WHEN rush THEN '!' ELSE '' END AS label FROM orders",
            line_width: 100,
            expected_sql: "SELECT\n  CASE\n    WHEN status = 'paid'\n    THEN 'customer paid in full'\n    WHEN status = 'open'\n    THEN 'customer has not paid yet'\n    ELSE 'other'\n  END\n  || CASE WHEN rush THEN '!' ELSE '' END AS label\nFROM orders",
        },
        test_types::LayoutRuleTestCase {
            description: "AND after a multi-line subquery starts the next line",
            dialect: "postgres",
            sql: "SELECT order_id FROM orders WHERE customer_id IN (SELECT customer_id FROM customers WHERE region = 'north') AND EXISTS (SELECT 1 FROM shipments)",
            line_width: 100,
            expected_sql: "SELECT order_id\nFROM orders\nWHERE\n  customer_id IN (\n    SELECT customer_id\n    FROM customers\n    WHERE region = 'north'\n  )\n  AND EXISTS(\n    SELECT 1\n    FROM shipments\n  )",
        },
        test_types::LayoutRuleTestCase {
            description: "BETWEEN bounds keep their AND",
            dialect: "snowflake",
            sql: "SELECT order_id FROM orders WHERE amount BETWEEN 1 AND 9",
            line_width: 100,
            expected_sql: "SELECT order_id\nFROM orders\nWHERE amount BETWEEN 1 AND 9",
        },
        test_types::LayoutRuleTestCase {
            description: "CTEs and the final statement are separated by one blank line",
            dialect: "duckdb",
            sql: "with orders as (select * from raw_orders),\n\n\n-- paid only\npaid as (select * from orders where amount > 0)\n\n\nselect * from paid",
            line_width: 100,
            expected_sql: "WITH orders AS (\n  SELECT *\n  FROM raw_orders\n),\n\n-- paid only\npaid AS (\n  SELECT *\n  FROM orders\n  WHERE amount > 0\n)\n\nSELECT *\nFROM paid",
        },
        test_types::LayoutRuleTestCase {
            description: "a trailing comment after a CTE comma keeps its line",
            dialect: "snowflake",
            sql: "WITH orders AS (SELECT * FROM raw_orders), -- raw\npaid AS (SELECT * FROM orders) SELECT * FROM paid",
            line_width: 100,
            expected_sql: "WITH orders AS (\n  SELECT *\n  FROM raw_orders\n), -- raw\n\npaid AS (\n  SELECT *\n  FROM orders\n)\n\nSELECT *\nFROM paid",
        },
        test_types::LayoutRuleTestCase {
            description: "a nested WITH is separated at its own indentation",
            dialect: "postgres",
            sql: "SELECT * FROM (WITH a AS MATERIALIZED (SELECT 1 AS x), b AS (SELECT x FROM a) SELECT x FROM b) AS nested",
            line_width: 100,
            expected_sql: "SELECT *\nFROM (\n  WITH a AS MATERIALIZED (\n    SELECT 1 AS x\n  ),\n\n  b AS (\n    SELECT x\n    FROM a\n  )\n\n  SELECT x\n  FROM b\n) AS nested",
        },
        test_types::LayoutRuleTestCase {
            description: "BigQuery recursive CTEs with column lists are separated",
            dialect: "bigquery",
            sql: "WITH RECURSIVE numbers (n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM numbers WHERE n < 3), doubled AS (SELECT n * 2 AS n FROM numbers) SELECT n FROM doubled",
            line_width: 100,
            expected_sql: "WITH RECURSIVE numbers (n) AS (\n  SELECT 1\n  UNION ALL\n  SELECT n + 1\n  FROM numbers\n  WHERE n < 3\n),\n\ndoubled AS (\n  SELECT n * 2 AS n\n  FROM numbers\n)\n\nSELECT n\nFROM doubled",
        },
        test_types::LayoutRuleTestCase {
            description: "a T-SQL WITH is separated before INSERT",
            dialect: "tsql",
            sql: "WITH paid AS (SELECT order_id FROM orders) INSERT INTO paid_orders SELECT order_id FROM paid",
            line_width: 100,
            expected_sql: "WITH paid AS (\n  SELECT order_id\n  FROM orders\n)\n\nINSERT INTO paid_orders\nSELECT order_id\nFROM paid",
        },
        test_types::LayoutRuleTestCase {
            description: "a CTE macro placeholder is separated like a CTE",
            dialect: "duckdb",
            sql: "WITH __sqb_lint_0__, paid AS (SELECT * FROM orders) SELECT * FROM paid",
            line_width: 100,
            expected_sql: "WITH\n__sqb_lint_0__,\n\npaid AS (\n  SELECT *\n  FROM orders\n)\n\nSELECT *\nFROM paid",
        },
        test_types::LayoutRuleTestCase {
            description: "an alias and comma that push a call over the width break the call",
            dialect: "snowflake",
            sql: "SELECT ARRAY_CONTAINS('web'::VARIANT, COALESCE(o.order_channels, ARRAY_CONSTRUCT())) AS has_web_channel, o.order_id FROM orders o",
            line_width: 80,
            expected_sql: "SELECT\n  ARRAY_CONTAINS(\n    'web'::VARIANT,\n    COALESCE(o.order_channels, ARRAY_CONSTRUCT())\n  ) AS has_web_channel,\n  o.order_id\nFROM orders o",
        },
        test_types::LayoutRuleTestCase {
            description: "an AND chain inside a call argument joins its line, then wraps",
            dialect: "snowflake",
            sql: "SELECT CAST(MAX(IFF(line_number = 1 AND shipped_after_days = 960, order_amount, NULL)) AS NUMBER(38, 10)) AS first_line_amount_shipped_late FROM orders",
            line_width: 100,
            expected_sql: "SELECT\n  CAST(\n    MAX(IFF(line_number = 1 AND shipped_after_days = 960, order_amount, NULL)) AS NUMBER(38, 10)\n  ) AS first_line_amount_shipped_late\nFROM orders",
        },
        test_types::LayoutRuleTestCase {
            description: "a one-line CASE over the width breaks at its branches",
            dialect: "duckdb",
            sql: "SELECT CASE WHEN o.shipped_at IS NULL THEN NULL WHEN o.refund_amount IS NULL THEN 0 ELSE 1 END AS has_refund FROM orders o",
            line_width: 80,
            expected_sql: "SELECT\n  CASE\n    WHEN o.shipped_at IS NULL\n    THEN NULL\n    WHEN o.refund_amount IS NULL\n    THEN 0\n    ELSE 1\n  END AS has_refund\nFROM orders o",
        },
        test_types::LayoutRuleTestCase {
            description: "a WITHIN GROUP line breaks the aggregate call",
            dialect: "snowflake",
            sql: "SELECT customer_id, LISTAGG(DISTINCT LOWER(product_category_name), ', ') WITHIN GROUP (ORDER BY product_category_name) AS categories FROM orders GROUP BY customer_id",
            line_width: 80,
            expected_sql: "SELECT\n  customer_id,\n  LISTAGG(\n    DISTINCT LOWER(product_category_name),\n    ', '\n  ) WITHIN GROUP (ORDER BY product_category_name) AS categories\nFROM orders\nGROUP BY\n  customer_id",
        },
        test_types::LayoutRuleTestCase {
            description: "a window that continues on later lines breaks at its clauses",
            dialect: "snowflake",
            sql: "SELECT ROW_NUMBER() OVER (PARTITION BY o.customer_id ORDER BY CASE o.status WHEN 'paid' THEN 0 WHEN 'open' THEN 1 ELSE 2 END, o.ordered_at DESC) AS rn FROM orders o",
            line_width: 60,
            expected_sql: "SELECT\n  ROW_NUMBER() OVER (\n    PARTITION BY o.customer_id\n    ORDER BY CASE o.status\n      WHEN 'paid'\n      THEN 0\n      WHEN 'open'\n      THEN 1\n      ELSE 2\n    END, o.ordered_at DESC\n  ) AS rn\nFROM orders o",
        },
        test_types::LayoutRuleTestCase {
            description: "SELECT * and a single WHERE condition share their clause lines",
            dialect: "duckdb",
            sql: "select * from orders where amount > 0",
            line_width: 100,
            expected_sql: "SELECT *\nFROM orders\nWHERE amount > 0",
        },
        test_types::LayoutRuleTestCase {
            description: "SELECT DISTINCT keeps its single item, several items break",
            dialect: "snowflake",
            sql: "SELECT DISTINCT order_id FROM orders WHERE amount > 0 AND status = 'paid' UNION ALL SELECT order_id, customer_id FROM returns",
            line_width: 100,
            expected_sql: "SELECT DISTINCT order_id\nFROM orders\nWHERE\n  amount > 0\n  AND status = 'paid'\nUNION ALL\nSELECT\n  order_id,\n  customer_id\nFROM returns",
        },
        test_types::LayoutRuleTestCase {
            description: "T-SQL TOP, HAVING and Snowflake-style single items share lines",
            dialect: "tsql",
            sql: "SELECT TOP 10 COUNT(*) AS n FROM orders GROUP BY customer_id HAVING COUNT(*) > 1",
            line_width: 100,
            expected_sql: "SELECT TOP 10 COUNT(*) AS n\nFROM orders\nGROUP BY\n  customer_id\nHAVING COUNT(*) > 1",
        },
        test_types::LayoutRuleTestCase {
            description: "QUALIFY with one condition shares its line",
            dialect: "databricks",
            sql: "SELECT order_id, ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY ordered_at) AS rn FROM orders QUALIFY rn = 1",
            line_width: 100,
            expected_sql: "SELECT\n  order_id,\n  ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY ordered_at) AS rn\nFROM orders\nQUALIFY rn = 1",
        },
        test_types::LayoutRuleTestCase {
            description: "a single item that does not fit stays under SELECT",
            dialect: "bigquery",
            sql: "SELECT COALESCE(first_order_amount, second_order_amount, third_order_amount) AS amount FROM orders WHERE first_order_amount + second_order_amount + third_order_amount > 100",
            line_width: 60,
            expected_sql: "SELECT\n  COALESCE(\n    first_order_amount,\n    second_order_amount,\n    third_order_amount\n  ) AS amount\nFROM orders\nWHERE\n  first_order_amount\n    + second_order_amount\n    + third_order_amount > 100",
        },
        test_types::LayoutRuleTestCase {
            description: "a short CASE item shares the SELECT line",
            dialect: "duckdb",
            sql: "SELECT CASE WHEN amount > 0 THEN 'paid' ELSE 'open' END AS status FROM orders",
            line_width: 100,
            expected_sql: "SELECT CASE WHEN amount > 0 THEN 'paid' ELSE 'open' END AS status\nFROM orders",
        },
        test_types::LayoutRuleTestCase {
            description: "a multi-line single item stays under SELECT",
            dialect: "duckdb",
            sql: "SELECT CASE WHEN amount > 1000 THEN 'large paid order' WHEN amount > 0 THEN 'paid order' ELSE 'open order' END AS status FROM orders",
            line_width: 100,
            expected_sql: "SELECT\n  CASE\n    WHEN amount > 1000\n    THEN 'large paid order'\n    WHEN amount > 0\n    THEN 'paid order'\n    ELSE 'open order'\n  END AS status\nFROM orders",
        },
    ];
    for test_case in &test_cases {
        let response: Value =
            format_at_width(test_case.sql, test_case.dialect, test_case.line_width)?;
        assert_eq!(response["formatted"], true, "{}", test_case.description);
        assert_eq!(
            response["sql"], test_case.expected_sql,
            "{}",
            test_case.description
        );
        assert_eq!(
            query_fingerprint(test_case.expected_sql, test_case.dialect)?,
            query_fingerprint(test_case.sql, test_case.dialect)?,
            "{}: layout changed the fingerprint",
            test_case.description
        );
        let again: Value = format_at_width(
            test_case.expected_sql,
            test_case.dialect,
            test_case.line_width,
        )?;
        assert_eq!(again["changed"], false, "{}", test_case.description);
    }
    Ok(())
}
