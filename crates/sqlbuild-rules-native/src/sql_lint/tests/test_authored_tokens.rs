use serde_json::{Value, json};

use crate::sql_lint::_helpers::token_layout::verify_token_invariant;
use crate::sql_lint::main::formatter::format_json;
use crate::sql_lint::tests::test_types;

#[test]
fn given_generator_respellings_when_formatting_then_authored_spellings_are_kept()
-> Result<(), String> {
    let test_cases = [
        test_types::FormatTestCase {
            description: "Snowflake STARTSWITH keeps its authored name",
            sql: "select startswith(order_code, 'EU') as is_eu_order from orders",
            expected_sql: "SELECT\n  startswith(order_code, 'EU') AS is_eu_order\nFROM orders",
            expected_changed: true,
        },
        test_types::FormatTestCase {
            description: "function synonyms keep their authored names",
            sql: "select SUBSTR(order_code, 1, 2) as region, TIMESTAMPDIFF(day, ordered_at, shipped_at) as days_to_ship, TRY_TO_DECIMAL(amount_text, 10, 2) as amount from orders",
            expected_sql: "SELECT\n  SUBSTR(order_code, 1, 2) AS region,\n  TIMESTAMPDIFF(day, ordered_at, shipped_at) AS days_to_ship,\n  TRY_TO_DECIMAL(amount_text, 10, 2) AS amount\nFROM orders",
            expected_changed: true,
        },
        test_types::FormatTestCase {
            description: "operator and function spellings stay authored",
            sql: "select IFNULL(status, 'open') as status from orders where quantity != 0",
            expected_sql: "SELECT\n  IFNULL(status, 'open') AS status\nFROM orders\nWHERE\n  quantity != 0",
            expected_changed: true,
        },
    ];
    for test_case in &test_cases {
        let response = format_json(
            &json!({"version": 1, "sql": test_case.sql, "dialect": "snowflake"}).to_string(),
        )?;
        let payload: Value = serde_json::from_str(&response).map_err(|error| error.to_string())?;
        assert_eq!(
            payload["sql"], test_case.expected_sql,
            "{}",
            test_case.description
        );
        assert_eq!(
            payload["changed"], test_case.expected_changed,
            "{}",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_generator_restructuring_when_formatting_then_authored_tokens_are_laid_out()
-> Result<(), String> {
    let test_cases = [
        test_types::DialectFormatTestCase {
            description: "PostgreSQL comma SUBSTRING arguments are not rewritten to FROM/FOR",
            dialect: "postgres",
            sql: "select substring(code, 1, 2) as region from orders",
            expected_sql: "SELECT\n  SUBSTRING(code, 1, 2) AS region\nFROM orders",
        },
        test_types::DialectFormatTestCase {
            description: "DuckDB SELECT ALL keeps ALL",
            dialect: "duckdb",
            sql: "select all order_id from orders",
            expected_sql: "SELECT ALL\n  order_id\nFROM orders",
        },
        test_types::DialectFormatTestCase {
            description: "Snowflake SELECT ALL keeps ALL",
            dialect: "snowflake",
            sql: "select all order_id from orders",
            expected_sql: "SELECT ALL\n  order_id\nFROM orders",
        },
        test_types::DialectFormatTestCase {
            description: "PostgreSQL SELECT ALL keeps ALL",
            dialect: "postgres",
            sql: "select all order_id from orders",
            expected_sql: "SELECT ALL\n  order_id\nFROM orders",
        },
        test_types::DialectFormatTestCase {
            description: "BigQuery SELECT ALL keeps ALL",
            dialect: "bigquery",
            sql: "select all order_id from orders",
            expected_sql: "SELECT ALL\n  order_id\nFROM orders",
        },
        test_types::DialectFormatTestCase {
            description: "Databricks SELECT ALL keeps ALL",
            dialect: "databricks",
            sql: "select all order_id from orders",
            expected_sql: "SELECT ALL\n  order_id\nFROM orders",
        },
        test_types::DialectFormatTestCase {
            description: "T-SQL SELECT ALL keeps ALL",
            dialect: "tsql",
            sql: "select all order_id from orders",
            expected_sql: "SELECT ALL\n  order_id\nFROM orders",
        },
        test_types::DialectFormatTestCase {
            description: "implicit aliases stay implicit",
            dialect: "duckdb",
            sql: "select order_id id, amount from orders o",
            expected_sql: "SELECT\n  order_id id,\n  amount\nFROM orders o",
        },
        test_types::DialectFormatTestCase {
            description: "a trailing select comma and statement terminator are kept",
            dialect: "duckdb",
            sql: "select order_id, amount, from orders;",
            expected_sql: "SELECT\n  order_id,\n  amount,\nFROM orders;",
        },
        test_types::DialectFormatTestCase {
            description: "adjacent authored tokens are never split",
            dialect: "duckdb",
            sql: "select $name as v from orders where status != 1",
            expected_sql: "SELECT\n  $name AS v\nFROM orders\nWHERE\n  status != 1",
        },
        test_types::DialectFormatTestCase {
            description: "BigQuery numeric-prefixed path parts stay joined",
            dialect: "bigquery",
            sql: "select * from orders.archive.25_",
            expected_sql: "SELECT\n  *\nFROM orders.archive.25_",
        },
    ];
    for test_case in &test_cases {
        let response = format_json(
            &json!({"version": 1, "sql": test_case.sql, "dialect": test_case.dialect}).to_string(),
        )?;
        let payload: Value = serde_json::from_str(&response).map_err(|error| error.to_string())?;
        assert_eq!(
            payload["sql"], test_case.expected_sql,
            "{}",
            test_case.description
        );
        let again = format_json(
            &json!({"version": 1, "sql": test_case.expected_sql, "dialect": test_case.dialect})
                .to_string(),
        )?;
        let repeated: Value = serde_json::from_str(&again).map_err(|error| error.to_string())?;
        assert_eq!(repeated["changed"], false, "{}", test_case.description);
    }
    Ok(())
}

#[test]
fn given_case_or_line_sensitive_tokens_when_formatting_then_they_are_kept_exactly()
-> Result<(), String> {
    let test_cases = [
        test_types::DialectFormatTestCase {
            description: "DuckDB keyword-named aliases and qualified names keep their case",
            dialect: "duckdb",
            sql: "select pos as index, sku as replace, t.view from orders t",
            expected_sql: "SELECT\n  pos AS index,\n  sku AS replace,\n  t.view\nFROM orders t",
        },
        test_types::DialectFormatTestCase {
            description: "BigQuery keyword-named table names keep their case",
            dialect: "bigquery",
            sql: "select * from inventory.view",
            expected_sql: "SELECT\n  *\nFROM inventory.view",
        },
        test_types::DialectFormatTestCase {
            description: "Snowflake path keys keep their case",
            dialect: "snowflake",
            sql: "select payload:Customer.Name as name, payload:Date::string as day from orders",
            expected_sql: "SELECT\n  payload:Customer.Name AS name,\n  payload:Date::string AS day\nFROM orders",
        },
        test_types::DialectFormatTestCase {
            description: "user-defined functions keep their case, built-ins are uppercased",
            dialect: "bigquery",
            sql: "select MyFunc(a), ds.MyUdf(b), coalesce(a, b) from orders",
            expected_sql: "SELECT\n  MyFunc(a),\n  ds.MyUdf(b),\n  COALESCE(a, b)\nFROM orders",
        },
        test_types::DialectFormatTestCase {
            description: "DuckDB adjacent string literals keep their line break",
            dialect: "duckdb",
            sql: "select 'north'\n'east' as region from orders",
            expected_sql: "SELECT\n  'north'\n  'east' AS region\nFROM orders",
        },
        test_types::DialectFormatTestCase {
            description: "PostgreSQL adjacent string literals keep their line break",
            dialect: "postgres",
            sql: "select 'north'\n  'east' as region from orders",
            expected_sql: "SELECT\n  'north'\n  'east' AS region\nFROM orders",
        },
        test_types::DialectFormatTestCase {
            description: "Snowflake double-slash comments are kept",
            dialect: "snowflake",
            sql: "select order_id, // keep this note\n customer_id from orders",
            expected_sql: "SELECT\n  order_id, // keep this note\n  customer_id\nFROM orders",
        },
        test_types::DialectFormatTestCase {
            description: "BigQuery hash comments are kept",
            dialect: "bigquery",
            sql: "select order_id, # keep this note\n customer_id from orders",
            expected_sql: "SELECT\n  order_id, # keep this note\n  customer_id\nFROM orders",
        },
        test_types::DialectFormatTestCase {
            description: "T-SQL temporary table hashes are not comments",
            dialect: "tsql",
            sql: "select #orders.order_id from #orders",
            expected_sql: "SELECT\n  #orders.order_id\nFROM #orders",
        },
        test_types::DialectFormatTestCase {
            description: "DuckDB integer division and slashes inside strings are not comments",
            dialect: "duckdb",
            sql: "select 7 // 2 as half, 'https://example.com/a' as url from orders",
            expected_sql: "SELECT\n  7 // 2 AS half,\n  'https://example.com/a' AS url\nFROM orders",
        },
        test_types::DialectFormatTestCase {
            description: "Snowflake double slashes inside strings are not comments",
            dialect: "snowflake",
            sql: "select 'https://example.com//a' as url from orders",
            expected_sql: "SELECT\n  'https://example.com//a' AS url\nFROM orders",
        },
    ];
    for test_case in &test_cases {
        let response = format_json(
            &json!({"version": 1, "sql": test_case.sql, "dialect": test_case.dialect}).to_string(),
        )?;
        let payload: Value = serde_json::from_str(&response).map_err(|error| error.to_string())?;
        assert_eq!(
            payload["sql"], test_case.expected_sql,
            "{}",
            test_case.description
        );
        let again = format_json(
            &json!({"version": 1, "sql": test_case.expected_sql, "dialect": test_case.dialect})
                .to_string(),
        )?;
        let repeated: Value = serde_json::from_str(&again).map_err(|error| error.to_string())?;
        assert_eq!(repeated["changed"], false, "{}", test_case.description);
    }
    Ok(())
}

#[test]
fn given_formatted_candidates_when_checking_token_invariant_then_only_layout_may_differ() {
    let test_cases = [
        test_types::TokenInvariantTestCase {
            description: "whitespace and word case may change",
            before: "select a,b from orders -- note",
            after: "SELECT\n  a,\n  b\nFROM orders -- note",
            expected_error: None,
        },
        test_types::TokenInvariantTestCase {
            description: "a renamed function is refused",
            before: "select startswith(code, 'EU') from orders",
            after: "SELECT STARTS_WITH(code, 'EU') FROM orders",
            expected_error: Some(
                "native formatter would change authored SQL tokens, not only layout",
            ),
        },
        test_types::TokenInvariantTestCase {
            description: "an added alias keyword is refused",
            before: "select a b from orders",
            after: "SELECT a AS b FROM orders",
            expected_error: Some(
                "native formatter would change authored SQL tokens, not only layout",
            ),
        },
        test_types::TokenInvariantTestCase {
            description: "string literal whitespace is refused",
            before: "select 'a  b' from orders",
            after: "SELECT 'a b' FROM orders",
            expected_error: Some(
                "native formatter would change authored SQL tokens, not only layout",
            ),
        },
        test_types::TokenInvariantTestCase {
            description: "an identifier case change is refused",
            before: "select a from orders",
            after: "SELECT a FROM Orders",
            expected_error: Some(
                "native formatter would change authored SQL tokens, not only layout",
            ),
        },
        test_types::TokenInvariantTestCase {
            description: "a path key case change is refused",
            before: "select payload:customerId from orders",
            after: "SELECT payload:CUSTOMERID FROM orders",
            expected_error: Some(
                "native formatter would change authored SQL tokens, not only layout",
            ),
        },
        test_types::TokenInvariantTestCase {
            description: "a built-in function may be recased",
            before: "select coalesce(a, 0) from orders",
            after: "SELECT COALESCE(a, 0) FROM orders",
            expected_error: None,
        },
        test_types::TokenInvariantTestCase {
            description: "joining adjacent string literals across a line break is refused",
            before: "select 'a'\n'b' from orders",
            after: "SELECT 'a' 'b' FROM orders",
            expected_error: Some(
                "native formatter would join adjacent string literals across a line break",
            ),
        },
        test_types::TokenInvariantTestCase {
            description: "a dropped double-slash comment is refused",
            before: "select a // note\nfrom orders",
            after: "SELECT a FROM orders",
            expected_error: Some("native formatter could not preserve comment token attachments"),
        },
        test_types::TokenInvariantTestCase {
            description: "a comment moved to another token is refused",
            before: "select a, -- note\n b from orders",
            after: "SELECT a, b -- note\nFROM orders",
            expected_error: Some("native formatter could not preserve comment token attachments"),
        },
    ];
    let dialect = polyglot_sql::Dialect::get(polyglot_sql::DialectType::Snowflake);
    for test_case in test_cases {
        let actual = verify_token_invariant(test_case.before, test_case.after, &dialect);
        assert_eq!(
            actual.err().as_deref(),
            test_case.expected_error,
            "{}",
            test_case.description
        );
    }
}
