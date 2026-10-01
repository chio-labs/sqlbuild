use crate::compiler::tests::helpers::{
    actual_probe_selects_zero_rows_from_step, difference_sample_lifts_expected_helper_ctes,
    difference_sample_lifts_generated_ctes_and_bounds_rows,
    ordered_comparison_batch_preserves_order, partial_expected_columns_project_both_sides,
    snowflake_plan_keeps_quoted_expected_columns,
    sqlserver_difference_sample_projects_bracketed_columns,
};
use crate::compiler::tests::helpers::{
    colliding_model_ctes_nest_on_nested_with_dialects, generated_with_bodies_stay_nested_verbatim,
    repeated_model_sql_renders_like_separate_batches, snowflake_function_synonyms_stay_as_authored,
    trailing_statement_terminators_are_dropped, tsql_distinct_ctes_lift_verbatim,
    tsql_fixture_and_model_cte_collisions_are_refused,
    tsql_identical_helper_ending_in_line_comment_is_shared,
    tsql_model_cte_collisions_are_renamed_by_token_span,
    tsql_unprovable_cte_renames_are_refused_with_named_ctes,
};
use crate::compiler::tests::test_types::SqlTestRenderingTestCase;

#[test]
fn given_sql_rendering_cases_when_rendering_native_batches_then_expected_behavior_holds() {
    let test_cases = [
        SqlTestRenderingTestCase {
            description: "colliding model CTEs use the nested fallback on nested-WITH dialects",
            run: colliding_model_ctes_nest_on_nested_with_dialects,
            expected_success: true,
        },
        SqlTestRenderingTestCase {
            description: "generated CTE bodies keep their own WITH nested verbatim",
            run: generated_with_bodies_stay_nested_verbatim,
            expected_success: true,
        },
        SqlTestRenderingTestCase {
            description: "T-SQL model CTE collisions are renamed by token span",
            run: tsql_model_cte_collisions_are_renamed_by_token_span,
            expected_success: true,
        },
        SqlTestRenderingTestCase {
            description: "T-SQL renames that cannot be proven safe are refused naming the CTEs",
            run: tsql_unprovable_cte_renames_are_refused_with_named_ctes,
            expected_success: true,
        },
        SqlTestRenderingTestCase {
            description: "T-SQL fixture and model CTE collisions are refused",
            run: tsql_fixture_and_model_cte_collisions_are_refused,
            expected_success: true,
        },
        SqlTestRenderingTestCase {
            description: "T-SQL identical helpers ending in a line comment are shared",
            run: tsql_identical_helper_ending_in_line_comment_is_shared,
            expected_success: true,
        },
        SqlTestRenderingTestCase {
            description: "trailing statement terminators are dropped from lifted bodies",
            run: trailing_statement_terminators_are_dropped,
            expected_success: true,
        },
        SqlTestRenderingTestCase {
            description: "distinct T-SQL CTEs lift verbatim, including brackets and comments",
            run: tsql_distinct_ctes_lift_verbatim,
            expected_success: true,
        },
        SqlTestRenderingTestCase {
            description: "Snowflake function synonyms stay exactly as authored",
            run: snowflake_function_synonyms_stay_as_authored,
            expected_success: true,
        },
        SqlTestRenderingTestCase {
            description: "repeated model SQL in one batch renders like separate batches",
            run: repeated_model_sql_renders_like_separate_batches,
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
