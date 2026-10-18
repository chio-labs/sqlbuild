use crate::compiler::main::scenario_expected_column_message::scenario_expected_column_message;
use crate::compiler::main::scenario_expected_columns::scenario_expected_columns;
use crate::compiler::tests::test_types::ScenarioExpectedColumnsTestCase;

#[test]
fn given_scenario_expected_cte_when_checking_columns_then_reports_unlisted_and_unknown() {
    let test_cases = [
        ScenarioExpectedColumnsTestCase {
            description: "every output column listed in another order and case",
            expected_sql: "SELECT FALSE AS Is_Cancelled, 'placed' AS status, 'o1' AS order_id",
            model_columns: Some(&["order_id", "status", "is_cancelled"]),
            all_columns: true,
            expected_message: None,
        },
        ScenarioExpectedColumnsTestCase {
            description: "an unlisted output column fails when every column is required",
            expected_sql: "SELECT 'o1' AS order_id, 'placed' AS status",
            model_columns: Some(&["order_id", "status", "is_cancelled"]),
            all_columns: true,
            expected_message: Some(
                "scenario 'flags' expected output __expected__order_flags does not list columns \
                 that model 'order_flags' outputs: is_cancelled",
            ),
        },
        ScenarioExpectedColumnsTestCase {
            description: "an unlisted output column is ignored when listed columns are compared",
            expected_sql: "SELECT 'o1' AS order_id, 'placed' AS status",
            model_columns: Some(&["order_id", "status", "is_cancelled"]),
            all_columns: false,
            expected_message: None,
        },
        ScenarioExpectedColumnsTestCase {
            description: "a listed column the model lacks always fails",
            expected_sql: "SELECT 'o1' AS order_id, 1 AS line_count",
            model_columns: Some(&["order_id", "status"]),
            all_columns: true,
            expected_message: Some(
                "scenario 'flags' expected output __expected__order_flags does not list columns \
                 that model 'order_flags' outputs: status; and lists columns that model \
                 'order_flags' does not output: line_count",
            ),
        },
        ScenarioExpectedColumnsTestCase {
            description: "an unknown model shape is not checked",
            expected_sql: "SELECT 'o1' AS order_id",
            model_columns: None,
            all_columns: true,
            expected_message: None,
        },
        ScenarioExpectedColumnsTestCase {
            description: "a star expected body is not checked",
            expected_sql: "SELECT * FROM __ref(\"orders\")",
            model_columns: Some(&["order_id", "status"]),
            all_columns: true,
            expected_message: None,
        },
    ];
    for test_case in test_cases {
        let model_columns: Option<Vec<String>> = test_case
            .model_columns
            .map(|columns| columns.iter().map(|column| (*column).to_owned()).collect());
        let columns = scenario_expected_columns(
            test_case.expected_sql,
            Some("duckdb"),
            model_columns.as_deref(),
        );
        assert_eq!(
            scenario_expected_column_message(
                "flags",
                "order_flags",
                &columns,
                test_case.all_columns
            )
            .as_deref(),
            test_case.expected_message,
            "{}",
            test_case.description
        );
    }
}
