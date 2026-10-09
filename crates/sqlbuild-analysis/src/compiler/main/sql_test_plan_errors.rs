//! The errors a planned SQL test reports.

use crate::compiler::_helpers::sql_tests::glue;
use crate::compiler::models::SqlTestPlan;

/// Each distinct error message of one planned test, in the order its warnings report them.
#[must_use]
pub fn sql_test_plan_error_messages(plan: &SqlTestPlan) -> Vec<String> {
    glue::error_messages(plan)
}
