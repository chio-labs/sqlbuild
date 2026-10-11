//! Fixed names the SQL-test attachment checks read.

/// The mode of a stored model SQL test classification.
pub(crate) const STORED_MODEL_MODE: &str = "model";
pub(crate) const REF_KIND: &str = "ref";
pub(crate) const SOURCE_KIND: &str = "source";
pub(crate) const SEED_KIND: &str = "seed";
pub(crate) const DBT_REF_KIND: &str = "dbt_ref";
pub(crate) const TABLE_FUNCTION_KIND: &str = "table_fn";
pub(crate) const REF_PREFIX: &str = "__ref__";
pub(crate) const MOCK_PREFIXES: [&str; 5] = [
    "__ref__",
    "__source__",
    "__seed__",
    "__dbt_ref__",
    "__table_fn__",
];
pub(crate) const TAB_SIZE: usize = 8;
