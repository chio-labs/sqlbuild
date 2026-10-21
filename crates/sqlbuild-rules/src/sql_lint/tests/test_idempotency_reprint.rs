use serde_json::{Value, json};

use crate::sql_lint::_helpers::formatter::RELAYOUTS;
use crate::sql_lint::main::formatter::format_json;
use crate::sql_lint::tests::test_types;

#[test]
fn given_formatted_and_unformatted_bodies_when_formatting_then_only_changed_bodies_are_reprinted()
-> Result<(), String> {
    let test_cases = [
        test_types::ReprintTestCase {
            description: "an already formatted body is not re-printed",
            sql: "SELECT\n  order_id,\n  amount\nFROM orders\nWHERE amount > 0",
            expected_changed: false,
            expected_reprints: 0,
        },
        test_types::ReprintTestCase {
            description: "a body the formatter changes is re-printed once",
            sql: "select order_id, amount from orders where amount > 0",
            expected_changed: true,
            expected_reprints: 1,
        },
    ];
    for test_case in &test_cases {
        RELAYOUTS.with(|relayouts| relayouts.set(0));
        let response = format_json(
            &json!({"version": 1, "sql": test_case.sql, "dialect": "duckdb"}).to_string(),
        )?;
        let payload: Value = serde_json::from_str(&response).map_err(|error| error.to_string())?;
        assert_eq!(
            payload["formatted"], true,
            "{}: {payload}",
            test_case.description
        );
        assert_eq!(
            payload["changed"], test_case.expected_changed,
            "{}: {payload}",
            test_case.description
        );
        assert_eq!(
            RELAYOUTS.with(std::cell::Cell::get),
            test_case.expected_reprints,
            "{}",
            test_case.description
        );
    }
    Ok(())
}
