//! SQL-test plan resource and severity decisions.

pub(super) const UDF: &str = "udf";
pub(super) const TABLE_FN: &str = "table_fn";
pub(super) const ERROR_SEVERITY: &str = "error";
pub(super) const COMPILE_MODELS: &str = "sqlbuild.compiler.compile.models";
pub(super) const COMPILE_TYPES: &str = "sqlbuild.compiler.compile.types";
pub(super) const PLAN_MODELS: &str = "sqlbuild.compiler.planner.models";
pub(super) const NATIVE_PLANNING: &str = "sqlbuild._native";
pub(super) const FIXTURE_VALIDATION: &str =
    "sqlbuild.compiler.planner._helpers.sql_tests.fixture_validation";
pub(super) const CURSOR_WINDOW: &str = "sqlbuild.compiler.planner._helpers.sql_tests.cursor_window";
pub(super) const SENTINEL: &str = "__SQLBUILD_CALL_SUFFIX__";
