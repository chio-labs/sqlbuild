use crate::compiler::tests::helpers::{
    chain_resolution_orders_unmocked_models, concurrent_requests_initialize_shared_template_once,
    deep_shared_graph_reports_missing_mock_once, long_chain_plan_output_stays_linear,
    model_test_batch_returns_ordered_artifact, plan_without_rendering_returns_executable_steps,
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
        SqlTestPlanningTestCase {
            description: "deep shared graph reports one missing mock once",
            run: deep_shared_graph_reports_missing_mock_once,
            expected_success: true,
        },
        SqlTestPlanningTestCase {
            description: "planning without rendering returns executable steps",
            run: plan_without_rendering_returns_executable_steps,
            expected_success: true,
        },
        SqlTestPlanningTestCase {
            description: "long chain plan output stays linear",
            run: long_chain_plan_output_stays_linear,
            expected_success: true,
        },
        SqlTestPlanningTestCase {
            description: "chain resolution orders unmocked models",
            run: chain_resolution_orders_unmocked_models,
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
