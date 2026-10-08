use crate::sql_tests::tests::helpers::{
    FILE_PATH, expected_rows, scenario_rows, statement_failures, test_file_rows,
};
use crate::sql_tests::tests::test_types::{DeepStatementHeaderTestCase, StatementFileTestCase};

#[test]
fn given_sql_test_files_when_splitting_then_blocks_and_failures_match_python() {
    let test_cases = [
        StatementFileTestCase {
            description: "blocks start at line starts and bodies are cleaned",
            contents: "\n TEST (name \"a\");\n    SELECT 1\n      FROM t\n\n  TEST(name \"b\") ;\n\tSELECT 2\n",
            expected_blocks: &[(&["name"], "SELECT 1\nFROM t"), (&["name"], "SELECT 2")],
            expected_failure: None,
        },
        StatementFileTestCase {
            description: "TEST not at a line start stays inside the previous body",
            contents: "TEST (name \"a\"); SELECT 'TEST (x);'",
            expected_blocks: &[(&["name"], "SELECT 'TEST (x);'")],
            expected_failure: None,
        },
        StatementFileTestCase {
            description: "content before the first header fails the file",
            contents: "-- lead\nTEST ();\nSELECT 1",
            expected_blocks: &[],
            expected_failure: Some(
                "SQL test 'project/tests/unit/orders.sql' must start with a TEST() header as the \
                 first non-whitespace content",
            ),
        },
        StatementFileTestCase {
            description: "an unsupported key stops at its block, at the key's line",
            contents: "TEST (name \"a\");\nSELECT 1\nTEST (\n  name \"b\",\n  nme 1\n);\nSELECT 2",
            expected_blocks: &[(&["name"], "SELECT 1")],
            expected_failure: Some(
                "TEST() in 'project/tests/unit/orders.sql:5' has unsupported keys: nme",
            ),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            test_file_rows(&test_case),
            expected_rows(test_case.expected_blocks, test_case.expected_failure),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_scenario_files_when_parsing_then_headers_and_failures_match_python() {
    let test_cases = [
        StatementFileTestCase {
            description: "the body keeps trailing indentation as cleandoc does",
            contents: "SCENARIO (description \"Orders\");\n\n  SELECT 1\n   ",
            expected_blocks: &[(&["description"], "SELECT 1\n   ")],
            expected_failure: None,
        },
        StatementFileTestCase {
            description: "a missing header fails",
            contents: "SELECT 1",
            expected_blocks: &[],
            expected_failure: Some(
                "SQL scenario 'project/tests/unit/orders.sql' must start with a SCENARIO() \
                 header as the first non-whitespace content",
            ),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            scenario_rows(&test_case),
            expected_rows(test_case.expected_blocks, test_case.expected_failure),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_deeply_nested_test_and_scenario_headers_when_parsing_then_each_reports_its_file_line() {
    let expected = |statement: &str| {
        Some((
            format!(
                "{statement}(...) in '{FILE_PATH}:3' contains invalid SQLBuild header syntax: \
                 values nest deeper than 256 levels"
            ),
            Some("flatten the value so it nests at most 256 levels deep".to_owned()),
        ))
    };
    let test_cases = [DeepStatementHeaderTestCase {
        description: "20k nested case maps",
        depth: 20_000,
        expected_failures: [expected("TEST"), expected("SCENARIO")],
    }];

    for test_case in test_cases {
        let contents: String = format!(
            "TEST (\n  name \"keeps_status\",\n  cases {}1{},\n);\n\nSELECT 1\n",
            "(case ".repeat(test_case.depth),
            ")".repeat(test_case.depth)
        );

        assert_eq!(
            statement_failures(&contents),
            test_case.expected_failures,
            "{}",
            test_case.description
        );
    }
}
