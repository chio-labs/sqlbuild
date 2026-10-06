use crate::sql_lint::tests::helpers::function_call_spacing;
use crate::sql_lint::tests::test_types;

#[test]
fn given_builtin_call_names_when_formatting_then_no_space_enters_the_call() -> Result<(), String> {
    let test_cases = [
        test_types::FunctionCallSpacingTestCase {
            description: "duckdb compact calls",
            dialect: "duckdb",
            line_width: 100,
            argument: "a",
            expected_refused: &[],
        },
        test_types::FunctionCallSpacingTestCase {
            description: "duckdb breaking calls",
            dialect: "duckdb",
            line_width: 40,
            argument: "order_amount_with_a_long_descriptive_name",
            expected_refused: &[],
        },
        test_types::FunctionCallSpacingTestCase {
            description: "snowflake compact calls",
            dialect: "snowflake",
            line_width: 100,
            argument: "a",
            expected_refused: &[],
        },
        test_types::FunctionCallSpacingTestCase {
            description: "snowflake breaking calls",
            dialect: "snowflake",
            line_width: 40,
            argument: "order_amount_with_a_long_descriptive_name",
            expected_refused: &[],
        },
        test_types::FunctionCallSpacingTestCase {
            description: "bigquery compact calls",
            dialect: "bigquery",
            line_width: 100,
            argument: "a",
            expected_refused: &[],
        },
        test_types::FunctionCallSpacingTestCase {
            description: "bigquery breaking calls",
            dialect: "bigquery",
            line_width: 40,
            argument: "order_amount_with_a_long_descriptive_name",
            expected_refused: &[],
        },
        test_types::FunctionCallSpacingTestCase {
            description: "postgres compact calls",
            dialect: "postgres",
            line_width: 100,
            argument: "a",
            expected_refused: &[],
        },
        test_types::FunctionCallSpacingTestCase {
            description: "postgres breaking calls",
            dialect: "postgres",
            line_width: 40,
            argument: "order_amount_with_a_long_descriptive_name",
            expected_refused: &[],
        },
        test_types::FunctionCallSpacingTestCase {
            description: "tsql compact calls",
            dialect: "tsql",
            line_width: 100,
            argument: "a",
            expected_refused: &[],
        },
        test_types::FunctionCallSpacingTestCase {
            description: "tsql breaking calls",
            dialect: "tsql",
            line_width: 40,
            argument: "order_amount_with_a_long_descriptive_name",
            expected_refused: &[],
        },
        test_types::FunctionCallSpacingTestCase {
            description: "databricks compact calls",
            dialect: "databricks",
            line_width: 100,
            argument: "a",
            expected_refused: &[],
        },
        test_types::FunctionCallSpacingTestCase {
            description: "databricks breaking calls",
            dialect: "databricks",
            line_width: 40,
            argument: "order_amount_with_a_long_descriptive_name",
            expected_refused: &[],
        },
        test_types::FunctionCallSpacingTestCase {
            description: "generic compact calls",
            dialect: "generic",
            line_width: 100,
            argument: "a",
            expected_refused: &[],
        },
        test_types::FunctionCallSpacingTestCase {
            description: "generic breaking calls",
            dialect: "generic",
            line_width: 40,
            argument: "order_amount_with_a_long_descriptive_name",
            expected_refused: &[],
        },
    ];
    for test_case in &test_cases {
        let (refused, misplaced) =
            function_call_spacing(test_case.dialect, test_case.line_width, test_case.argument)?;
        assert_eq!(
            refused, test_case.expected_refused,
            "{}",
            test_case.description
        );
        assert_eq!(misplaced, Vec::<String>::new(), "{}", test_case.description);
    }
    Ok(())
}
