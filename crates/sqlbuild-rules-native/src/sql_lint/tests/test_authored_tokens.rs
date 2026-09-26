use serde_json::{Value, json};

use crate::sql_lint::_helpers::formatter::preserve_authored_tokens;
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
            expected_sql: "SELECT\n  SUBSTR(order_code, 1, 2) AS region,\n  TIMESTAMPDIFF(DAY, ordered_at, shipped_at) AS days_to_ship,\n  TRY_TO_DECIMAL(amount_text, 10, 2) AS amount\nFROM orders",
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
fn given_generated_token_changes_when_preserving_authored_tokens_then_only_layout_survives() {
    let dialect = polyglot_sql::Dialect::get(polyglot_sql::DialectType::Snowflake);
    let test_cases = [
        test_types::AuthoredTokenTestCase {
            description: "renamed function is restored to its authored spelling",
            authored: "select startswith(code, 'EU') from orders",
            generated: "SELECT\n  STARTS_WITH(code, 'EU')\nFROM orders",
            expected_sql: Some("SELECT\n  startswith(code, 'EU')\nFROM orders"),
        },
        test_types::AuthoredTokenTestCase {
            description: "swapped arguments are restored to authored order",
            authored: "select datediff(day, a, b) from orders",
            generated: "SELECT\n  DATEDIFF(DAY, b, a)\nFROM orders",
            expected_sql: Some("SELECT\n  DATEDIFF(DAY, a, b)\nFROM orders"),
        },
        test_types::AuthoredTokenTestCase {
            description: "an explicit alias keyword may be added",
            authored: "select a b from orders",
            generated: "SELECT\n  a AS b\nFROM orders",
            expected_sql: Some("SELECT\n  a AS b\nFROM orders"),
        },
        test_types::AuthoredTokenTestCase {
            description: "a structural change refuses the format",
            authored: "select a from orders where a <> 1",
            generated: "SELECT\n  a\nFROM orders\nWHERE\n  NOT a = 1",
            expected_sql: None,
        },
        test_types::AuthoredTokenTestCase {
            description: "a dropped token refuses the format",
            authored: "select a from orders left outer join items using (id)",
            generated: "SELECT\n  a\nFROM orders\nLEFT JOIN items USING (id)",
            expected_sql: None,
        },
    ];
    for test_case in test_cases {
        let actual = preserve_authored_tokens(
            test_case.authored,
            test_case.generated.to_string(),
            &dialect,
        );
        assert_eq!(
            actual.ok().as_deref(),
            test_case.expected_sql,
            "{}",
            test_case.description
        );
    }
}
