use crate::semantic_checks::tests::helpers::projected_type;
use crate::semantic_checks::tests::test_types::ArgumentTypeTestCase;

#[test]
fn given_argument_expressions_when_typing_then_matches_python_expression_types() {
    let test_cases = [
        ArgumentTypeTestCase {
            description: "a sized VARCHAR cast",
            expression: "CAST(a AS VARCHAR(10))",
            expected_type: Some("VARCHAR(10)"),
        },
        ArgumentTypeTestCase {
            description: "a DECIMAL cast with precision and scale",
            expression: "CAST(a AS DECIMAL(10, 2))",
            expected_type: Some("DECIMAL(10, 2)"),
        },
        ArgumentTypeTestCase {
            description: "a DECIMAL cast with precision only",
            expression: "CAST(a AS DECIMAL(10))",
            expected_type: Some("DECIMAL(10)"),
        },
        ArgumentTypeTestCase {
            description: "a TRY_CAST to a zoned timestamp",
            expression: "TRY_CAST(a AS TIMESTAMPTZ)",
            expected_type: Some("TIMESTAMPTZ"),
        },
        ArgumentTypeTestCase {
            description: "an unzoned timestamp cast",
            expression: "CAST(a AS TIMESTAMP)",
            expected_type: Some("TIMESTAMP"),
        },
        ArgumentTypeTestCase {
            description: "a BIGINT cast",
            expression: "CAST(a AS BIGINT)",
            expected_type: Some("BIGINT"),
        },
        ArgumentTypeTestCase {
            description: "a custom type is upper-cased",
            expression: "CAST(a AS my_type)",
            expected_type: Some("MY_TYPE"),
        },
        ArgumentTypeTestCase {
            description: "an unmapped serialised name is spaced and upper-cased",
            expression: "CAST(a AS HUGEINT)",
            expected_type: Some("INT128"),
        },
        ArgumentTypeTestCase {
            description: "a comparison is Boolean",
            expression: "a = 1",
            expected_type: Some("BOOLEAN"),
        },
        ArgumentTypeTestCase {
            description: "a declared function return type",
            expression: "my_fn(a)",
            expected_type: Some("DATE"),
        },
        ArgumentTypeTestCase {
            description: "arithmetic has no inferred type",
            expression: "a + 1",
            expected_type: None,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            projected_type(test_case.expression).as_deref(),
            test_case.expected_type,
            "{}",
            test_case.description
        );
    }
}
