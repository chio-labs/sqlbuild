//! Reference kinds audit validation reads and the cross-resource audit threshold.

pub(crate) const REF_KIND: &str = "ref";
pub(crate) const SEED_KIND: &str = "seed";
pub(crate) const SOURCE_KIND: &str = "source";
pub(crate) const DBT_REF_KIND: &str = "dbt_ref";
pub(crate) const TABLE_FUNCTION_KIND: &str = "table_fn";
pub(crate) const MODEL_RESOURCE: &str = "model";
pub(crate) const SOURCE_RESOURCE: &str = "source";
pub(crate) const SEED_RESOURCE: &str = "seed";
pub(crate) const FUNCTION_RESOURCE: &str = "function";
pub(crate) const RELATIONSHIPS_AUDIT: &str = "relationships";
pub(crate) const RELATIONSHIPS_TARGET_ARGUMENT: &str = "to";
/// The calls that make a `relationships` target a dependency on a built relation.
pub(crate) const RELATION_REFERENCE_CALLS: [&str; 4] =
    ["__ref(", "__source(", "__seed(", "__dbt_ref("];
/// Singular audits reading fewer models must also read a companion resource.
pub(crate) const CROSS_MODEL_MINIMUM: usize = 2;
/// The run scope Python falls back to without an instance or project value.
pub(crate) const FALLBACK_RUN_SCOPE: &str = "delta_and_final";
/// Built-in generic audit names and SQL bodies, which project definitions override by name.
pub const BUILTIN_AUDITS: [(&str, &str); 4] = [
    (
        "accepted_values",
        "SELECT @column\nFROM @relation\nWHERE @column IS NOT NULL\n  AND @column NOT IN (@'values')",
    ),
    (
        "not_null",
        "SELECT @column\nFROM @relation\nWHERE @column IS NULL",
    ),
    (
        "relationships",
        "SELECT @column\nFROM @relation\nWHERE @column IS NOT NULL\n  AND @column NOT IN (\n    SELECT @field\n    FROM @to\n    WHERE @field IS NOT NULL\n  )",
    ),
    (
        "unique",
        "SELECT @column, COUNT(*) AS duplicate_count\nFROM @relation\nWHERE @column IS NOT NULL\nGROUP BY @column\nHAVING COUNT(*) > 1",
    ),
];
