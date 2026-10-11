//! Resource kinds, codes and wording Python's explicit-reference checks use.

pub(crate) const MODEL_TYPE: &str = "model";
pub(crate) const SOURCE_TYPE: &str = "source";
pub(crate) const SEED_TYPE: &str = "seed";
pub(crate) const UDF_TYPE: &str = "udf";
pub(crate) const TABLE_FUNCTION_TYPE: &str = "table_fn";
pub(crate) const SQL_TEST_TYPE: &str = "sql_test";
/// Resource types an attached audit's extra reads can gate on.
pub(crate) const READABLE_TYPES: [&str; 5] = [
    MODEL_TYPE,
    SEED_TYPE,
    SOURCE_TYPE,
    UDF_TYPE,
    TABLE_FUNCTION_TYPE,
];
pub(crate) const AUDIT_GATE_CODE: &str = "P005";
pub(crate) const HOOK_READ_CODE: &str = "P007";
pub(crate) const HARD_CODED_RELATION_CODE: &str = "P008";
pub(crate) const LOADER_OWNER: &str = "loader";
pub(crate) const HOOK_OWNER: &str = "hook";
pub(crate) const PYTHON_DESTINATION: &str = "ctx.destination";
pub(crate) const SQL_DESTINATION: &str = "@@CTX:destination.qualified";
/// The quotes Python strips from each `migrate_from` part.
pub(crate) const MIGRATE_FROM_QUOTES: [char; 2] = ['"', '`'];
pub(crate) const SCHEMA_QUALIFIED_PARTS: usize = 2;
