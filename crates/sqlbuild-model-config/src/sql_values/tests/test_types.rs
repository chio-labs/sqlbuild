use crate::sql_values::errors::SqlValueFailure;
use crate::sql_values::models::RawSqlValue;
use sqlbuild_core::models::SqlValue;

pub(super) struct NormalizeTestCase {
    pub(super) description: &'static str,
    pub(super) raw: RawSqlValue,
    pub(super) explicit_type: Option<&'static str>,
    pub(super) expected_value: Result<SqlValue, SqlValueFailure>,
}
