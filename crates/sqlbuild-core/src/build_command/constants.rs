//! Build command codes, policy values and fixed text.

pub const POLICY_ALLOW: &str = "allow";
pub const POLICY_REQUIRE_CONFIRMATION: &str = "require_confirmation";
pub const POLICY_DENY: &str = "deny";

pub(crate) const MIGRATION_ORIGIN_MISSING: &str = "origin_missing";
pub(crate) const MIGRATION_CONFLICT: &str = "conflict";
pub(crate) const MIGRATION_CODE: &str = "M102";
pub(crate) const MIGRATION_CONFLICT_CODE: &str = "M103";
pub(crate) const MIGRATION_INCOMPATIBLE_CODE: &str = "M104";
pub(crate) const OLD_NAME_CODES: [&str; 2] = ["M114", "P008"];
pub(crate) const OLD_NAME_DEFAULT_CODE: &str = "M114";
pub(crate) const COLUMN_BLOCK_CODES: [(&str, &str); 4] = [
    ("source_missing", "M109"),
    ("conflict", "M110"),
    ("still_produced", "M111"),
    ("unsupported", "M112"),
];
pub(crate) const COLUMN_BLOCK_DEFAULT_CODE: &str = "M109";
pub(crate) const SNAPSHOT_DENIED_CODE: &str = "C238";
pub(crate) const SNAPSHOT_CONFIRMATION_CODE: &str = "C239";
pub(crate) const SNAPSHOT_CANCELLED_CODE: &str = "C240";
pub(crate) const MODEL_LIMIT_CODE: &str = "C413";
pub(crate) const DURATION_UNSUPPORTED_CODE: &str = "C415";
pub(crate) const DURATION_EXCEEDED_CODE: &str = "C416";
pub(crate) const DEFAULT_TARGET_LABEL: &str = "default";

pub(crate) const HIDDEN_ORIGIN_REMEDY: &str = "the connection may lack permission to see it, or it was dropped outside SQLBuild; restore access to it, or remove migrate_from to build the model fresh deliberately (missing_migration_origin does not apply)";
pub(crate) const MIGRATION_PLAN_HELP: &str = "Run sqb plan to see every model migration decision.";
pub(crate) const MIGRATION_CONFLICT_HELP: &str = "Set migrate_force true on the model to replace the destination; the replaced table remains recoverable through warehouse time travel.";
pub(crate) const MIGRATION_INCOMPATIBLE_HELP: &str =
    "Run sqb plan to see the blocking schema differences.";
pub(crate) const COLUMN_MIGRATION_HELP: &str =
    "Run sqb plan to see why each column rename cannot be applied.";
pub(crate) const OLD_NAME_HELP: &str =
    "Run sqb plan to see every compatibility view and old-name reference.";
pub(crate) const SNAPSHOT_DENIED_HELP: &str = "Set a less strict project/model snapshot_full_refresh policy only if the snapshot history is recoverable.";
pub(crate) const RETENTION_DENIED_HELP: &str = "Keep the current retention, or set the target's time_travel_retention_decrease to 'require_confirmation' or 'allow'.";

/// Label width of the verbose phase timing rows.
pub(crate) const PHASE_LABEL_WIDTH: usize = 24;
/// Label width of the verbose execution context rows.
pub(crate) const CONTEXT_LABEL_WIDTH: usize = 12;
pub(crate) const NOT_SET: &str = "not set";
pub(crate) const C0_CONTROL_CODE_LIMIT: u32 = 0x20;
pub(crate) const C1_CONTROL_CODE_START: u32 = 0x7f;
pub(crate) const C1_CONTROL_CODE_LIMIT: u32 = 0xa0;

pub(crate) const PYTHON_NODE_SUCCESS: &str = "success";
pub(crate) const PYTHON_NODE_SKIPPED: &str = "skipped";
pub(crate) const PYTHON_NODE_FAILED: &str = "failed";
pub(crate) const PYTHON_STATUS_OK: &str = "OK";
pub(crate) const PYTHON_STATUS_SKIP: &str = "SKIP";
pub(crate) const PYTHON_STATUS_FAIL: &str = "FAIL";
