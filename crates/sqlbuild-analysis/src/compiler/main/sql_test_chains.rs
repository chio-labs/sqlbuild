//! SQL-test model chains for compiled projects, from a typed request.

use crate::compiler::_helpers::sql_tests::planning;
use crate::compiler::models::SqlTestChainBatch;

/// Each test's ordered unmocked model chain; direct-logic tests have none.
pub fn resolve_sql_test_chains(request: SqlTestChainBatch) -> Result<Vec<Vec<String>>, String> {
    planning::resolve_chains(request)
}
