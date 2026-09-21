use crate::compiler::tests::helpers::{
    dynamic_or_malformed_sql_requests_fallback, scalar_variables_preserve_lexical_boundaries,
};
use crate::compiler::tests::test_types::StaticSqlOperationTestCase;

#[test]
fn given_sql_interpolation_cases_when_substituting_then_expected_behavior_holds() {
    let test_cases = [
        StaticSqlOperationTestCase {
            description: "scalar variables preserve lexical boundaries",
            run: scalar_variables_preserve_lexical_boundaries,
            expected_success: true,
        },
        StaticSqlOperationTestCase {
            description: "dynamic and malformed SQL requests Python fallback",
            run: dynamic_or_malformed_sql_requests_fallback,
            expected_success: true,
        },
    ];

    for test_case in test_cases {
        let actual_success = (test_case.run)();
        assert_eq!(
            actual_success, test_case.expected_success,
            "{}",
            test_case.description
        );
    }
}
