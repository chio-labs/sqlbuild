pub(super) const PLANNER_MODELS: &str = "sqlbuild._native";
pub(super) const MIGRATION_TYPES: &str = "sqlbuild._native";
pub(super) const AUTOMATIC: &str = "automatic";
pub(super) const DONE: &str = "done";
pub(super) const PENDING_ARCHIVE: &str = "pending_archive";
pub(super) const PENDING_VIEW: &str = "pending_view";
pub(super) const NATIVE_MODULE: &str = "sqlbuild._native";
pub(super) const FINGERPRINT_TABLE_NAME: &str = "_sqlbuild_fingerprints";
pub(super) const NODE_TYPE_MODEL: &str = "model";
pub(super) const LIST_RELATIONS_FOR_INSPECTION: (&str, &str) = (
    "sqlbuild.adapter.relations.main._list_relations_for_inspection",
    "list_relations_for_inspection",
);
pub(super) const GET_COLUMNS_FOR_INSPECTION: (&str, &str) = (
    "sqlbuild.adapter.relations.main._get_columns_for_inspection",
    "get_columns_for_inspection",
);
pub(super) const QUALIFIED_RELATION_MAX_PARTS: usize = 3;
pub(super) const MIGRATION_MODEL_NAME_METADATA_KEY: &str = "model_name";
pub(super) const HIDDEN_ORIGIN_REMEDY: &str = "the connection may lack permission to see it, or it was dropped outside SQLBuild; restore access to it, or remove migrate_from to build the model fresh deliberately (missing_migration_origin does not apply)";
pub(super) const MISSING_ORIGIN_ALLOW_OUTCOME: &str = "nothing is migrated and the build continues as if migrate_from were absent; remove migrate_from once no target still needs it";
pub(super) const MISSING_ORIGIN_CONFIRMATION_OUTCOME: &str = "building without it needs confirmation (missing_migration_origin = require_confirmation); pass --allow-missing-migration-origin, or remove migrate_from if it is no longer needed";
pub(super) const MISSING_ORIGIN_DENY_OUTCOME: &str = "the build stops (missing_migration_origin = deny); if the migration already happened elsewhere or is no longer needed, remove migrate_from";
