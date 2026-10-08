use crate::compiler::tests::helpers::{
    dollar_quoted_text_is_quoted_for_substitution, dynamic_or_malformed_sql_requests_fallback,
    scalar_variables_preserve_lexical_boundaries, unclosed_dollar_quote_requests_fallback,
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
        StaticSqlOperationTestCase {
            description: "dollar-quoted text is quoted text, not comments or code",
            run: dollar_quoted_text_is_quoted_for_substitution,
            expected_success: true,
        },
        StaticSqlOperationTestCase {
            description: "unclosed dollar quotes request Python fallback",
            run: unclosed_dollar_quote_requests_fallback,
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
