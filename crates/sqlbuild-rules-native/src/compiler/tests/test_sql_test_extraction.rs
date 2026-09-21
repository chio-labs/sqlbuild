use crate::compiler::tests::helpers::{
    dependent_assertion_returns_authoritative_error,
    mixed_expanded_tests_preserve_order_and_payloads,
    quoted_ctes_and_implicit_alias_preserve_payload,
};
use crate::compiler::tests::test_types::SqlTestExtractionTestCase;

#[test]
fn given_sql_test_cases_when_extracting_native_payloads_then_expected_behavior_holds() {
    let test_cases = [
        SqlTestExtractionTestCase {
            description: "mixed expanded tests preserve order and payloads",
            run: mixed_expanded_tests_preserve_order_and_payloads,
            expected_success: true,
        },
        SqlTestExtractionTestCase {
            description: "dependent assertions return the authoritative error",
            run: dependent_assertion_returns_authoritative_error,
            expected_success: true,
        },
        SqlTestExtractionTestCase {
            description: "quoted CTEs and implicit aliases preserve payloads",
            run: quoted_ctes_and_implicit_alias_preserve_payload,
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
