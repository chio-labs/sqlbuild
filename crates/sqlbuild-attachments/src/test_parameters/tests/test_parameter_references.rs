use crate::test_parameters::main::parameter_references::parameter_references;
use crate::test_parameters::tests::helpers::spans;
use crate::test_parameters::tests::test_types::ParameterReferenceTestCase;

#[test]
fn given_test_sql_when_scanning_parameters_then_python_references_are_returned() {
    let test_cases = [
        ParameterReferenceTestCase {
            description: "references by code point, quotes and comments skipped",
            sql: "SELECT 'é@param(\"x\")', @param ( \"region\" ) -- @param(\"x\")\n, @param(\"limit\")",
            expected_references: Some(vec![(23, 42, "region"), (60, 75, "limit")]),
        },
        ParameterReferenceTestCase {
            description: "a longer identifier is not a reference",
            sql: "SELECT @params, @param_x",
            expected_references: Some(vec![]),
        },
        ParameterReferenceTestCase {
            description: "a malformed reference defers so Python raises",
            sql: "SELECT @param(region)",
            expected_references: None,
        },
        ParameterReferenceTestCase {
            description: "an undeclared parameter defers so Python raises",
            sql: "SELECT @param(\"missing\")",
            expected_references: None,
        },
        ParameterReferenceTestCase {
            description: "an unclosed quote defers so Python raises",
            sql: "SELECT 'open",
            expected_references: None,
        },
    ];

    for test_case in test_cases {
        let declared: Vec<String> = vec!["region".to_owned(), "limit".to_owned()];
        assert_eq!(
            spans(parameter_references(test_case.sql, &declared)),
            test_case.expected_references.map(|references| {
                references
                    .into_iter()
                    .map(|(start, end, name)| (start, end, name.to_owned()))
                    .collect()
            }),
            "{}",
            test_case.description
        );
    }
}
