use crate::compiler::tests::helpers::{
    actual_probe_selects_zero_rows_from_step,
    difference_sample_lifts_generated_ctes_and_bounds_rows,
    ordered_comparison_batch_preserves_order, partial_expected_columns_project_both_sides,
    snowflake_plan_keeps_quoted_expected_columns,
    sqlserver_difference_sample_projects_bracketed_columns,
};
use crate::compiler::tests::test_types::SqlTestRenderingTestCase;

#[test]
fn given_sql_rendering_cases_when_rendering_native_batches_then_expected_behavior_holds() {
    let test_cases = [
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
