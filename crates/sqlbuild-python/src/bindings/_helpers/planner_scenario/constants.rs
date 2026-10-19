//! Relation categories with additional scenario binding semantics.

pub(super) const REF: &str = "ref";
pub(super) const SOURCE: &str = "source";
pub(super) const SOURCE_MARKER: usize = 2;
pub(super) const DBT_REF: &str = "dbt_ref";
pub(super) const SCENARIO_PLAN_INVALID_HASH_PREFIX: &str = "S501";
pub(super) const SCENARIO_PLAN_HASH_COLLISION: &str = "S502";
pub(super) const SCENARIO_PLAN_RELATION_COLLISION: &str = "S503";
pub(super) const SCENARIO_PLAN_GRAPH_VALIDATION: &str = "S504";
pub(super) const SCENARIO_PLAN_UNKNOWN_SEED: &str = "S507";
pub(super) const SCENARIO_PLAN_MISSING_FIXTURE_SQL: &str = "S508";
pub(super) const SCENARIO_PLAN_MISSING_RELATION_TARGET: &str = "S509";
pub(super) const SCENARIO_PLAN_INVALID_FIXTURE: &str = "S510";
pub(super) const SCENARIO_PLAN_UNRESOLVED_RELATION_MARKER: &str = "S511";
pub(super) const SCENARIO_PLAN_EXPECTED_COLUMNS: &str = "S512";
pub(super) const SCENARIO_EXPECTED_COLUMNS_HELP: &str = "list every column the model outputs in the expected CTE, and remove columns it does not output";
pub(super) const SCENARIO_PLAN_INTERNAL: &str = "S599";
