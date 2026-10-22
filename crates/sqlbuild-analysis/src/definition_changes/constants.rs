//! Node kinds, definition aspects and the snapshot format version.

/// The version of the stored snapshot layout and fingerprint scheme; older snapshots are recomputed.
pub const DEFINITION_SNAPSHOT_FORMAT: u32 = 1;

pub const MODEL_KIND: &str = "model";
pub const SEED_KIND: &str = "seed";
pub const UDF_KIND: &str = "udf";
pub const TABLE_FUNCTION_KIND: &str = "table_fn";
pub const MACRO_KIND: &str = "macro";
pub const ENUM_KIND: &str = "enum";
pub const CONSTANT_KIND: &str = "constant";
pub const TEST_FILE_KIND: &str = "test_file";
pub const SCENARIO_KIND: &str = "scenario";

/// Normalised SQL of a model, a function body or a scenario.
pub const SQL_ASPECT: &str = "sql";
/// Header configuration, without descriptions.
pub const CONFIG_ASPECT: &str = "config";
/// Declared columns and contract, without descriptions.
pub const COLUMNS_ASPECT: &str = "columns";
/// Attached audits, without descriptions.
pub const AUDITS_ASPECT: &str = "audits";
/// The whole definition of a seed, function, macro, enum or constant.
pub const DEFINITION_ASPECT: &str = "definition";
/// The authored file of a test or scenario.
pub const FILE_ASPECT: &str = "file";
/// Captured local snapshots of a scenario.
pub const SNAPSHOTS_ASPECT: &str = "snapshots";

/// How each aspect reads in a reason, in the order reasons list them.
pub(crate) const ASPECT_LABELS: [(&str, &str); 7] = [
    (SQL_ASPECT, "SQL"),
    (CONFIG_ASPECT, "config"),
    (COLUMNS_ASPECT, "columns"),
    (AUDITS_ASPECT, "audits"),
    (DEFINITION_ASPECT, "definition"),
    (FILE_ASPECT, "file"),
    (SNAPSHOTS_ASPECT, "snapshots"),
];

/// How each node kind reads in summaries: singular, plural.
pub(crate) const KIND_LABELS: [(&str, &str, &str); 14] = [
    (MODEL_KIND, "model", "models"),
    (SEED_KIND, "seed", "seeds"),
    (UDF_KIND, "function", "functions"),
    (TABLE_FUNCTION_KIND, "table function", "table functions"),
    (MACRO_KIND, "macro", "macros"),
    (ENUM_KIND, "enum", "enums"),
    (CONSTANT_KIND, "constant", "constants"),
    ("audit", "audit", "audits"),
    ("singular_audit", "singular audit", "singular audits"),
    ("schema", "schema", "schemas"),
    ("sql_hook", "SQL hook", "SQL hooks"),
    ("python_hook", "Python hook", "Python hooks"),
    (TEST_FILE_KIND, "test file", "test files"),
    (SCENARIO_KIND, "scenario", "scenarios"),
];
