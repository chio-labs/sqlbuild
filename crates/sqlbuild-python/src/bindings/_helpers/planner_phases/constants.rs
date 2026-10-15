//! Python modules and names the planner phases exchange values with.

pub(crate) const NATIVE_MODULE: &str = "sqlbuild._native";
pub(crate) const PLANNER_MODELS: &str = "sqlbuild.compiler.planner.models";
pub(crate) const PLANNER_TYPES: &str = "sqlbuild.compiler.planner.types";
pub(crate) const PLANNER_EXCEPTIONS: &str = "sqlbuild.compiler.planner.exceptions";
pub(crate) const ADAPTER_MODELS: &str = "sqlbuild.adapter.contract.models";
pub(crate) const ADAPTER_TYPES: &str = "sqlbuild.adapter.contract.types";
pub(crate) const SPEC_MODELS: &str = "sqlbuild.spec.contracts.models";
pub(crate) const PLAN_ENTRY_MODULE: &str = "sqlbuild.compiler.planner._helpers.output.plan_entry";
pub(crate) const PLAN_OUTPUT_MODULE: &str = "sqlbuild.compiler.planner._helpers.output.plan_output";
pub(crate) const SNOWFLAKE_ADAPTER: &str = "snowflake";
pub(crate) const BIGQUERY_ADAPTER: &str = "bigquery";
pub(crate) const TRANSIENT_TABLE_TYPE: &str = "transient";
pub(crate) const PERMANENT_TABLE_TYPE: &str = "permanent";
pub(crate) const DECREASE_WARNING: &str =
    "Retention decreases are irreversible once warehouse history expires.";
pub(crate) const DOWNGRADE_HISTORY_DAYS: i64 = 90;
pub(crate) const FULL_REFRESH_DISABLED_REBUILD_CODE: &str = "S203";
pub(crate) const MISSING_UPSTREAM_CODE: &str = "S301";
pub(crate) const RETENTION_DECREASE: &str = "decrease";
pub(crate) const RETENTION_INCREASE: &str = "increase";
pub(crate) const RETENTION_MATCH: &str = "match";
