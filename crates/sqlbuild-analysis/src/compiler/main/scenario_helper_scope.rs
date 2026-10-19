//! Index a scenario file's helper and fixture CTEs for the queries that read them.

use crate::compiler::_helpers::sql_tests::scenario_scope::helper_scope;
use crate::compiler::models::ScenarioHelperScope;
use crate::compiler::models::ScenarioScopeInput;

/// The scenario's helper scope, or why a CTE cannot be placed, such as a shadowed helper.
pub fn scenario_helper_scope(
    input: &ScenarioScopeInput<'_>,
) -> Result<ScenarioHelperScope, String> {
    helper_scope(input)
}
