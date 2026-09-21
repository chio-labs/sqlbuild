use crate::compiler::tests::helpers::ordered_comparison_batch_preserves_order;
use crate::compiler::tests::test_types::SqlTestRenderingTestCase;

#[test]
fn given_sql_rendering_cases_when_rendering_native_batches_then_expected_behavior_holds() {
    let test_cases = [SqlTestRenderingTestCase {
        description: "ordered comparison batches preserve SQL order",
        run: ordered_comparison_batch_preserves_order,
        expected_success: true,
    }];

    for test_case in test_cases {
        let actual_success = (test_case.run)();
        assert_eq!(
            actual_success, test_case.expected_success,
            "{}",
            test_case.description
        );
    }
}
