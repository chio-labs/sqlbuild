use crate::compiler::tests::helpers::{
    comments_and_quoted_text_hide_references, complex_or_malformed_sql_requests_fallback,
    simple_references_preserve_authored_order,
};
use crate::compiler::tests::test_types::StaticSqlOperationTestCase;

#[test]
fn given_sql_reference_cases_when_extracting_then_expected_behavior_holds() {
    let test_cases = [
        StaticSqlOperationTestCase {
            description: "simple references preserve authored order",
            run: simple_references_preserve_authored_order,
            expected_success: true,
        },
        StaticSqlOperationTestCase {
            description: "comments and quoted text hide embedded references",
            run: comments_and_quoted_text_hide_references,
            expected_success: true,
        },
        StaticSqlOperationTestCase {
            description: "complex and malformed SQL requests Python fallback",
            run: complex_or_malformed_sql_requests_fallback,
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
