//! Python's resource, reference and target constants the project assembly reproduces.

pub(crate) const MODEL_RESOURCE: &str = "model";
pub(crate) const SOURCE_KIND: &str = "source";
pub(crate) const SEED_KIND: &str = "seed";
pub(crate) const DBT_REF_KIND: &str = "dbt_ref";
pub(crate) const UDF_KIND: &str = "udf";
pub(crate) const TABLE_FUNCTION_KIND: &str = "table_fn";
/// The reference kinds whose dependency keeps the reference's kind as its resource type.
pub(crate) const KIND_RESOURCES: [&str; 4] =
    [SOURCE_KIND, SEED_KIND, UDF_KIND, TABLE_FUNCTION_KIND];
/// `AttachedAuditTargetKind` values, each also its resource type.
pub(crate) const ATTACHED_AUDIT_KINDS: [&str; 3] = [MODEL_RESOURCE, SOURCE_KIND, SEED_KIND];
pub(crate) const PRESERVE_TARGET_VALUE: &str = "preserve";
pub(crate) const TEMPLATE_OPEN_TOKEN: &str = "${";
pub(crate) const PYTHON_NONE: &str = "None";
pub(crate) const PYTHON_TRUE: &str = "True";
pub(crate) const PYTHON_FALSE: &str = "False";
pub(crate) const PLACEHOLDER_PREFIX: &str = "@@@";
pub(crate) const MAX_FUNCTION_CALL_DEPTH: usize = 512;
pub(crate) const MODEL_NAME_CONTEXT: &str = "model.name";
pub(crate) const MODEL_DATABASE_CONTEXT: &str = "model.database";
pub(crate) const MODEL_SCHEMA_CONTEXT: &str = "model.schema";
pub(crate) const MODEL_ALIAS_CONTEXT: &str = "model.alias";
pub(crate) const DESTINATION_DATABASE_CONTEXT: &str = "destination.database";
pub(crate) const DESTINATION_SCHEMA_CONTEXT: &str = "destination.schema";
pub(crate) const DESTINATION_TABLE_CONTEXT: &str = "destination.table";
pub(crate) const DESTINATION_QUALIFIED_CONTEXT: &str = "destination.qualified";
pub(crate) const AUDIT_TARGET_DEFERRAL: &str = "audit_target_kind";
pub(crate) const TEMPLATE_DEFERRAL: &str = "target_template";
/// `render_project_var_text` of booleans inside a larger template string.
pub(crate) const PROJECT_VAR_TRUE: &str = "true";
pub(crate) const PROJECT_VAR_FALSE: &str = "false";
/// The label template errors would name; assembly defers every template error.
pub(crate) const TEMPLATE_LABEL: &str = "project assembly template";
pub(crate) const PRESERVED_NAMESPACE_DEFERRAL: &str = "preserved_namespace";
pub(crate) const SYNTAX_DEFERRAL: &str = "syntax_error";
pub(crate) const PLACEHOLDER_DEFERRAL: &str = "placeholder_word";
pub(crate) const NORMALIZATION_DEFERRAL: &str = "normalization";
pub(crate) const DIALECT_DEFERRAL: &str = "dialect";
pub(crate) const UNSUPPORTED_DIALECT_DEFERRAL: &str = "unsupported_dialect";
pub(crate) const PANIC_DEFERRAL: &str = "panic";
