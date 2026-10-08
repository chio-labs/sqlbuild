use crate::test_parameters::main::parameter_references::parameter_references;
use crate::test_parameters::tests::helpers::spans;
use crate::test_parameters::tests::test_types::ParameterReferenceTestCase;

const OWNER: &str = "SQL test 'orders' case 'basic' in 'tests/orders.sql'";

#[test]
fn given_test_sql_when_scanning_parameters_then_python_references_and_error_are_returned() {
    let test_cases = [
        ParameterReferenceTestCase {
            description: "references by code point, quotes and comments skipped",
            sql: "SELECT 'é@param(\"x\")', @param ( \"region\" ) -- @param(\"x\")\n, @param(\"limit\")",
            expected_references: vec![(23, 42, "region"), (60, 75, "limit")],
            expected_error: None,
        },
        ParameterReferenceTestCase {
            description: "a longer identifier is not a reference",
            sql: "SELECT @params, @param_x",
            expected_references: vec![],
            expected_error: None,
        },
        ParameterReferenceTestCase {
            description: "a malformed reference stops after the references before it",
            sql: "SELECT @param(\"region\"), @param(region), @param(\"missing\")",
            expected_references: vec![(7, 23, "region")],
            expected_error: Some(
                "SQL test 'orders' case 'basic' in 'tests/orders.sql' has malformed @param \
                 reference; expected @param(\"name\")",
            ),
        },
        ParameterReferenceTestCase {
            description: "an undeclared parameter names itself",
            sql: "SELECT @param(\"missing\"), 'open",
            expected_references: vec![],
            expected_error: Some(
                "SQL test 'orders' case 'basic' in 'tests/orders.sql' references undeclared \
                 parameter 'missing'",
            ),
        },
        ParameterReferenceTestCase {
            description: "an unclosed quote is Python's plain SQL quote error",
            sql: "SELECT @param(\"limit\"), 'open",
            expected_references: vec![(7, 22, "limit")],
            expected_error: Some("SQL contains an unclosed quoted string"),
        },
        ParameterReferenceTestCase {
            description: "an unclosed block comment is Python's plain SQL comment error",
            sql: "SELECT 1 /* open",
            expected_references: vec![],
            expected_error: Some("SQL contains an unclosed block comment"),
        },
    ];

    for test_case in test_cases {
        let declared: Vec<String> = vec!["region".to_owned(), "limit".to_owned()];
        assert_eq!(
            spans(parameter_references(test_case.sql, &declared, OWNER)),
            (
                test_case
                    .expected_references
                    .into_iter()
                    .map(|(start, end, name)| (start, end, name.to_owned()))
                    .collect(),
                test_case.expected_error.map(str::to_owned)
            ),
            "{}",
            test_case.description
        );
    }
}
