use crate::compiler::tests::helpers::{
    concurrent_requests_initialize_shared_template_once, model_test_batch_returns_ordered_artifact,
    shared_textual_chain_renders_each_model_once,
    unicode_cte_after_leading_with_preserves_identifier,
    unresolved_reference_fast_rejection_preserves_warning,
};
use crate::compiler::tests::test_types::SqlTestPlanningTestCase;

#[test]
fn given_sql_test_planning_cases_when_exercising_native_planner_then_expected_behavior_holds() {
    let test_cases = [
        SqlTestPlanningTestCase {
            description: "concurrent requests initialize the shared template once",
            run: concurrent_requests_initialize_shared_template_once,
            expected_success: true,
        },
        SqlTestPlanningTestCase {
            description: "model test batches return ordered artifacts",
            run: model_test_batch_returns_ordered_artifact,
            expected_success: true,
        },
        SqlTestPlanningTestCase {
            description: "Unicode CTE identifiers survive leading WITH extraction",
            run: unicode_cte_after_leading_with_preserves_identifier,
            expected_success: true,
        },
        SqlTestPlanningTestCase {
            description: "shared textual chain renders each upstream model once",
            run: shared_textual_chain_renders_each_model_once,
            expected_success: true,
        },
        SqlTestPlanningTestCase {
            description: "fast rejection preserves unresolved reference warnings",
            run: unresolved_reference_fast_rejection_preserves_warning,
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
