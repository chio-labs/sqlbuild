//! dbt manifest v12 constants.

pub(crate) const DBT_MANIFEST_SCHEMA_VERSION: &str =
    "https://schemas.getdbt.com/dbt/manifest/v12.json";
pub(crate) const DBT_VERSION: &str = "1.12.0";
pub(crate) const RESOURCE_TYPE_MODEL: &str = "model";
pub(crate) const RESOURCE_TYPE_SOURCE: &str = "source";
pub(crate) const RESOURCE_TYPE_SEED: &str = "seed";
pub(crate) const RESOURCE_TYPE_TEST: &str = "test";
pub(crate) const RESOURCE_TYPE_MACRO: &str = "macro";
pub(crate) const CHECKSUM_HASH_NAME: &str = "sha256";
/// Compiled resource type to its dbt unique id prefix; any other type uses `model`.
pub(crate) const RESOURCE_TYPE_PREFIXES: [(&str, &str); 6] = [
    ("model", "model"),
    ("source", "source"),
    ("seed", "seed"),
    ("dbt_ref", "model"),
    ("audit", "test"),
    ("sql_test", "test"),
];
pub(crate) const DEFAULT_RESOURCE_PREFIX: &str = "model";
/// The package suffix SQL hook macros are published under.
pub(crate) const SQL_HOOK_PACKAGE_SUFFIX: &str = "__sqlbuild_hooks";
/// The meta key SQLBuild-owned facts are nested under.
pub(crate) const SQLBUILD_META_KEY: &str = "sqlbuild";
/// `json.dumps(..., indent=2)`.
pub(crate) const MANIFEST_INDENT: usize = 2;
