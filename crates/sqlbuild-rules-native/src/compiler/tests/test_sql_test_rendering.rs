use crate::compiler::tests::helpers::{
    actual_probe_selects_zero_rows_from_step, difference_sample_lifts_expected_helper_ctes,
    difference_sample_lifts_generated_ctes_and_bounds_rows,
    ordered_comparison_batch_preserves_order, partial_expected_columns_project_both_sides,
    snowflake_plan_keeps_quoted_expected_columns,
    sqlserver_difference_sample_projects_bracketed_columns,
};
use crate::compiler::tests::helpers::{
    bounded_names_are_unique, model_cte_names_are_isolated_across_dialects,
    quoted_names_keep_bindings,
};
use crate::compiler::tests::test_types::SqlTestRenderingTestCase;

#[test]
fn given_sql_rendering_cases_when_rendering_native_batches_then_expected_behavior_holds() {
    let test_cases = [
        SqlTestRenderingTestCase {
            description: "model CTEs are isolated across every first-class dialect",
            run: model_cte_names_are_isolated_across_dialects,
            expected_success: true,
        },
        SqlTestRenderingTestCase {
            description: "long and reserved CTE names are bounded, unique and deterministic",
            run: bounded_names_are_unique,
            expected_success: true,
        },
        SqlTestRenderingTestCase {
            description: "quoted CTEs and literals retain their bindings",
            run: quoted_names_keep_bindings,
            expected_success: true,
        },
        SqlTestRenderingTestCase {
            description: "ordered comparison batches preserve SQL order",
            run: ordered_comparison_batch_preserves_order,
            expected_success: true,
        },
        SqlTestRenderingTestCase {
            description: "difference samples lift generated CTEs and bound rows",
            run: difference_sample_lifts_generated_ctes_and_bounds_rows,
            expected_success: true,
        },
        SqlTestRenderingTestCase {
            description: "partial expected columns project both comparison sides",
            run: partial_expected_columns_project_both_sides,
            expected_success: true,
        },
        SqlTestRenderingTestCase {
            description: "actual probe selects zero rows from the step",
            run: actual_probe_selects_zero_rows_from_step,
            expected_success: true,
        },
        SqlTestRenderingTestCase {
            description: "SQL Server difference sample projects bracketed columns",
            run: sqlserver_difference_sample_projects_bracketed_columns,
            expected_success: true,
        },
        SqlTestRenderingTestCase {
            description: "Snowflake plan keeps quoted expected columns",
            run: snowflake_plan_keeps_quoted_expected_columns,
            expected_success: true,
        },
        SqlTestRenderingTestCase {
            description: "difference samples lift expected helper CTEs",
            run: difference_sample_lifts_expected_helper_ctes,
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
