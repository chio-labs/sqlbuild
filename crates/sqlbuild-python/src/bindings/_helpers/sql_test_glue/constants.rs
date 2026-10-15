//! SQL-test plan resource and severity decisions.

pub(super) const UDF: &str = "udf";
pub(super) const TABLE_FN: &str = "table_fn";
pub(super) const ERROR_SEVERITY: &str = "error";
pub(super) const COMPILE_MODELS: &str = "sqlbuild.compiler.compile.models";
pub(super) const COMPILE_TYPES: &str = "sqlbuild.compiler.compile.types";
pub(super) const PLAN_MODELS: &str = "sqlbuild.compiler.planner.models";
pub(super) const NATIVE_PLANNING: &str = "sqlbuild._native";
pub(super) const FIXTURE_PREFIXES: [(&str, &str); 4] = [
    ("model", "__ref__"),
    ("source", "__source__"),
    ("seed", "__seed__"),
    ("sql_test", "__expected__"),
];
pub(super) const CURSOR_ALGEBRA_EXCEPTIONS: &str = "sqlbuild.cursor_algebra.exceptions";
pub(super) const PLANNER_TYPES: &str = "sqlbuild.compiler.planner.types";
pub(super) const INTEGER_CURSOR_TYPE: &str = "integer";
pub(super) const TIMESTAMP_CURSOR_TYPE: &str = "timestamp";
pub(super) const DEFAULT_TIMESTAMP_START: &str = "1900-01-01 00:00:00";
pub(super) const DEFAULT_TIMESTAMP_END: &str = "2999-12-31 00:00:00";
pub(super) const DEFAULT_INTEGER_START: &str = "-1000000000000000";
pub(super) const DEFAULT_INTEGER_END: &str = "1000000000000000";
pub(super) const CURSOR_START_KEY: &str = "cursor_start";
pub(super) const CURSOR_END_KEY: &str = "cursor_end";
pub(super) const SENTINEL: &str = "__SQLBUILD_CALL_SUFFIX__";
