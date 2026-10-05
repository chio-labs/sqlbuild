use crate::compiler::tests::helpers::{
    batch_offsets_count_code_points, declaration_references_follow_the_expansion_walk,
    dialect_comments_hide_references, dialect_escaped_reference_names_request_fallback,
    malformed_or_unicode_declarations_request_fallback,
    sql_without_declarations_skips_unclosed_text,
};
use crate::compiler::tests::test_types::StaticSqlOperationTestCase;

#[test]
fn given_model_rendering_cases_when_scanning_natively_then_expected_behavior_holds() {
    let test_cases = [
        StaticSqlOperationTestCase {
            description: "declaration references follow the expansion walk",
            run: declaration_references_follow_the_expansion_walk,
            expected_success: true,
        },
        StaticSqlOperationTestCase {
            description: "malformed or Unicode-sensitive declarations request Python fallback",
            run: malformed_or_unicode_declarations_request_fallback,
            expected_success: true,
        },
        StaticSqlOperationTestCase {
            description: "SQL without declarations skips unclosed text like Python",
            run: sql_without_declarations_skips_unclosed_text,
            expected_success: true,
        },
        StaticSqlOperationTestCase {
            description: "batch offsets count code points",
            run: batch_offsets_count_code_points,
            expected_success: true,
        },
        StaticSqlOperationTestCase {
            description: "dialect comments hide references",
            run: dialect_comments_hide_references,
            expected_success: true,
        },
        StaticSqlOperationTestCase {
            description: "dialect-escaped reference names request Python fallback",
            run: dialect_escaped_reference_names_request_fallback,
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
