//! dbt manifest resource types and the help SQLBuild shows for manifest problems.

pub const MODEL_RESOURCE_TYPE: &str = "model";
pub const SNAPSHOT_RESOURCE_TYPE: &str = "snapshot";
pub const SEED_RESOURCE_TYPE: &str = "seed";
pub const SOURCE_RESOURCE_TYPE: &str = "source";
pub const TEST_RESOURCE_TYPE: &str = "test";
pub const UNIT_TEST_RESOURCE_TYPE: &str = "unit_test";
/// Node fields read as text: identity, namespace, relation and SQL.
pub const NODE_TEXT_FIELDS: [&str; 13] = [
    "package_name",
    "name",
    "source_name",
    "database",
    "schema",
    "alias",
    "identifier",
    "relation_name",
    "raw_code",
    "compiled_code",
    "raw_sql",
    "compiled_sql",
    "resource_type",
];
pub(crate) const MANIFEST_HELP: &str =
    "Run dbt compile or configure dbt target_path so SQLBuild can read manifest.json.";
pub(crate) const DBT_REF_FUNCTION: &str = "__dbt_ref";
