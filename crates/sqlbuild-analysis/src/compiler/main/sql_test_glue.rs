//! SQL-test planning for compiled projects, from a typed request.

use crate::compiler::_helpers::sql_tests::planning;
use crate::compiler::models::{SqlTestPlanBatch, SqlTestPlanBatchOutcome};

/// Plan every test of `request` in request order; errors carry the planner's message prefixes.
pub fn plan_sql_test_batch(request: SqlTestPlanBatch) -> Result<SqlTestPlanBatchOutcome, String> {
    planning::plan_batch(request)
}
