//! Python modules and fixed names of warehouse inspection for planning.

pub(crate) const RELATIONS_MAIN_LIST: (&str, &str) = (
    "sqlbuild.adapter.relations.main._list_relations_for_inspection",
    "list_relations_for_inspection",
);
pub(crate) const RELATIONS_MAIN_COLUMNS: (&str, &str) = (
    "sqlbuild.adapter.relations.main._get_columns_for_inspection",
    "get_columns_for_inspection",
);
pub(crate) const ACTIVE_CATALOG: (&str, &str) = (
    "sqlbuild.adapter.relations.main.active_inspection_catalog",
    "active_inspection_catalog",
);
pub(crate) const RUN_BOUNDED: (&str, &str) = (
    "sqlbuild.adapter.relations.main.run_bounded_inspections",
    "run_bounded_inspections",
);
pub(crate) const RECORD_QUERY: (&str, &str) = (
    "sqlbuild.adapter.relations.main.record_inspection_query",
    "record_inspection_query",
);
pub(crate) const RUN_RECORDED_QUERY: (&str, &str) = (
    "sqlbuild.adapter.relations.main.run_recorded_inspection_query",
    "run_recorded_inspection_query",
);
pub(crate) const QUERY_RECORD: (&str, &str) =
    ("sqlbuild.adapter.relations.models", "InspectionQueryRecord");
pub(crate) const COLUMN_INFO: (&str, &str) = ("sqlbuild.adapter.contract.models", "ColumnInfo");
pub(crate) const RELATION_LOOKUP: (&str, &str) =
    ("sqlbuild.adapter.contract.models", "RelationLookup");
pub(crate) const LOG_DEBUG_EVENT: (&str, &str) = (
    "sqlbuild.diagnostics.main.log_debug_event",
    "log_debug_event",
);
pub(crate) const CURSOR_RESOLVE_MODULE: &str = "sqlbuild._native";
pub(crate) const CURSOR_POLICIES: (&str, &str) =
    ("sqlbuild._native", "resolve_start_cursor_config");
pub(crate) const MAXIMUM_START: (&str, &str) = ("sqlbuild._native", "maximum_allowed_start");
pub(crate) const RENDER_SOURCE_READ: (&str, &str) =
    ("sqlbuild._native", "render_source_read_relation");
pub(crate) const YAML_ENTRY_LINE: (&str, &str) = ("sqlbuild._native", "yaml_entry_line");
pub(crate) const RUN_SCOPE: (&str, &str) =
    ("sqlbuild.runtime.observability.main.run_scope", "run_scope");
pub(crate) const SQL_HOOK_ENTRY: (&str, &str) =
    ("sqlbuild.compiler.discovery.models", "SqlHookEntry");
pub(crate) const CURSOR_ALGEBRA_ERROR: (&str, &str) =
    ("sqlbuild.cursor_algebra.exceptions", "CursorAlgebraError");
pub(crate) const DATE_VALUE: (&str, &str) = ("sqlbuild.cursor_algebra.models", "DateValue");
pub(crate) const PLANNER_LOGGER: &str = "sqlbuild.planner";
pub(crate) const FINGERPRINT_TABLE_NAME: &str = "_sqlbuild_fingerprints";
pub(crate) const SOURCE_FRESHNESS_TABLE_NAME: &str = "_sqlbuild_source_freshness";
pub(crate) const OLD_NAME_VIEW_TABLE_NAME: &str = "_sqlbuild_old_name_views";
pub(crate) const MIGRATION_TABLE_NAME: &str = "_sqlbuild_migrations";
pub(crate) const METADATA_NAME_FILTER_LIMIT: usize = 250;
pub(crate) const NODE_TYPE_MODEL: &str = "model";
pub(crate) const NODE_TYPE_SEED: &str = "seed";
pub(crate) const FUNCTION_NODE_TYPES: [&str; 2] = ["udf", "table_fn"];
pub(crate) const WILDCARD_TABLE_CHARACTER: &str = "*";
pub(crate) const MIGRATE_FROM_CONFIG_KEY: &str = "migrate_from";
pub(crate) const MODEL_HOOK_CONFIG_KEYS: [&str; 2] = ["pre_hooks", "post_hooks"];
pub(crate) const CURSOR_TYPE_TIMESTAMP: &str = "timestamp";
pub(crate) const CURSOR_TYPE_INTEGER: &str = "integer";
pub(crate) const MISSING_SOURCE_TABLE_CODE: &str = "S405";
pub(crate) const WATERMARK_CONTRACT_CODE: &str = "S302";
