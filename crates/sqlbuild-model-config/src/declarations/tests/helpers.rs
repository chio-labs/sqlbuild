use crate::sql_values::models::{RawKey, RawSqlValue};

/// A header `enums` mapping with one enum.
pub(super) fn enums(name: &str, members: RawSqlValue) -> RawSqlValue {
    RawSqlValue::Object(vec![(RawKey::Str(name.to_owned()), members)])
}
