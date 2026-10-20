//! Config keys, labels and context names the model config build reads and writes.

pub(crate) const HOOK_KEYS: [&str; 2] = ["pre_hooks", "post_hooks"];
/// Hook keys in the sorted order `validate_model_hook_config` checks them.
pub(crate) const SORTED_HOOK_KEYS: [&str; 2] = ["post_hooks", "pre_hooks"];
pub(crate) const MODEL_CONFIG_LABEL: &str = "model config";
pub(crate) const ENVIRONMENT_DATABASE_LABEL: &str = "environment database";
pub(crate) const ENVIRONMENT_SCHEMA_LABEL: &str = "environment schema";
pub(crate) const TAGS_KEY: &str = "tags";
pub(crate) const DATABASE_KEY: &str = "database";
pub(crate) const SCHEMA_KEY: &str = "schema";
pub(crate) const ALIAS_KEY: &str = "alias";
pub(crate) const MATERIALIZED_KEY: &str = "materialized";
pub(crate) const FULL_REFRESH_KEY: &str = "full_refresh";
pub(crate) const RETENTION_KEY: &str = "time_travel_retention";
pub(crate) const TABLE_TYPE_KEY: &str = "table_type";
pub(crate) const INCREMENTAL_MATERIALIZATION: &str = "incremental";
pub(crate) const PRESERVE_TARGET_VALUE: &str = "preserve";
pub(crate) const TEMPLATE_OPEN_TOKEN: &str = "${";
pub(crate) const ENVIRONMENT_READ: &str = "env";
pub(crate) const CONTEXT_READ: &str = "ctx";
pub(crate) const RUN_ID_CONTEXT: &str = "run.id";
pub(crate) const RUN_TARGET_CONTEXT: &str = "run.target";
pub(crate) const MODEL_NAME_CONTEXT: &str = "model.name";
pub(crate) const MODEL_DATABASE_CONTEXT: &str = "model.database";
pub(crate) const MODEL_SCHEMA_CONTEXT: &str = "model.schema";
pub(crate) const MODEL_ALIAS_CONTEXT: &str = "model.alias";
pub(crate) const DESTINATION_DATABASE_CONTEXT: &str = "destination.database";
pub(crate) const DESTINATION_SCHEMA_CONTEXT: &str = "destination.schema";
pub(crate) const DESTINATION_TABLE_CONTEXT: &str = "destination.table";
pub(crate) const DESTINATION_QUALIFIED_CONTEXT: &str = "destination.qualified";
