pub const COLUMNS_UNKNOWN: &str =
    "Output columns could not be inferred, so the fix cannot be verified";
pub const COLUMNS_CHANGED: &str = "The fix would change output columns, types or nullability";
pub const DEPENDENCIES_CHANGED: &str = "The fix would change model dependencies";
pub const LINEAGE_CHANGED: &str = "The fix would change column lineage";
pub const NEW_DIAGNOSTICS: &str = "The fix would add compile diagnostics: ";
