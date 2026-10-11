//! SQL `TEST(...)` header keys, modes and the actual CTEs that infer a mode.

pub(crate) const NAME_KEY: &str = "name";
pub(crate) const MODE_KEY: &str = "mode";
pub(crate) const SQL_ANALYSIS_KEY: &str = "sql_analysis";
pub(crate) const PARAMETERS_KEY: &str = "parameters";
pub(crate) const CASES_KEY: &str = "cases";
pub(crate) const CURSOR_START_KEY: &str = "cursor_start";
pub(crate) const CURSOR_END_KEY: &str = "cursor_end";
pub(crate) const TYPE_OPTION: &str = "type";
pub(crate) const NULLABLE_OPTION: &str = "nullable";
/// `SqlTestMode` values, in declaration order.
pub(crate) const SQL_TEST_MODES: [&str; 4] = ["model", "macro", "udf", "table_fn"];
pub(crate) const MODEL_MODE: &str = "model";
/// Each direct-logic actual CTE name and the mode it infers, in Python's dict order.
pub(crate) const ACTUAL_CTE_MODES: [(&str, &str); 3] = [
    ("__macro_actual__", "macro"),
    ("__udf_actual__", "udf"),
    ("__table_fn_actual__", "table_fn"),
];
/// Text every actual CTE name contains.
pub(crate) const ACTUAL_CTE_MARKER: &str = "_actual__";
/// The scalar kinds a test parameter may declare, in `SqlValueKind` order.
pub(crate) const PARAMETER_TYPES: [&str; 5] = ["string", "integer", "boolean", "float", "decimal"];
/// Every `SqlValueKind` value.
pub(crate) const SQL_VALUE_KINDS: [&str; 9] = [
    "string", "integer", "boolean", "float", "decimal", "null", "list", "set", "object",
];
