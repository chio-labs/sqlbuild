//! One scenario query preceded by the helper and fixture CTEs it reads.

use crate::compiler::_helpers::sql_tests::cte_sql::with_leading_ctes;
use crate::compiler::main::scenario_reader_ctes::scenario_reader_ctes;
use crate::compiler::models::ScenarioHelperScope;

/// `sql` with the CTEs it reads ahead of it, merged into its own leading WITH.
#[must_use]
pub fn scenario_reader_sql(scope: &ScenarioHelperScope, sql: &str, fixtures: bool) -> String {
    with_leading_ctes(&scenario_reader_ctes(scope, sql, fixtures), sql)
}
