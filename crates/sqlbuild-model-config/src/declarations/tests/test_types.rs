use crate::declarations::errors::DeclarationFailure;
use crate::sql_values::models::RawSqlValue;

pub(super) struct HeaderEnumTestCase {
    pub(super) description: &'static str,
    pub(super) raw: RawSqlValue,
    pub(super) expected_scalar_types: Result<Vec<&'static str>, DeclarationFailure>,
}
