//! Typed SQL literals for state event columns, as `render_state_sql_literal` writes them.

use sqlbuild_cursor::algebra::models::LocalDateTime;

use crate::events::constants::{
    ESCAPED_QUOTE, NULL_LITERAL, QUOTE, STRING_VALUE_REQUIRED, TIMESTAMP_VALUE_REQUIRED, UTC_SUFFIX,
};
use crate::events::errors::StateSqlError;
use crate::events::models::{StateColumnType, StateValue};

/// `value` in single quotes with embedded quotes doubled.
pub(crate) fn quoted(value: &str) -> String {
    format!("{QUOTE}{}{QUOTE}", value.replace(QUOTE, ESCAPED_QUOTE))
}

/// `datetime.isoformat()` of a UTC timestamp.
pub(crate) fn utc_isoformat(local: &LocalDateTime) -> String {
    let date = &local.date;
    let mut text: String = format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}",
        date.year, date.month, date.day, local.hour, local.minute, local.second
    );
    if local.microsecond != 0 {
        text.push_str(&format!(".{:06}", local.microsecond));
    }
    text.push_str(UTC_SUFFIX);
    text
}

/// One value as the literal its declared column type takes.
pub(crate) fn literal(
    column_type: StateColumnType,
    value: &StateValue,
) -> Result<String, StateSqlError> {
    match (column_type, value) {
        (_, StateValue::Null) => Ok(NULL_LITERAL.to_owned()),
        (StateColumnType::String, StateValue::Text(text)) => Ok(quoted(text)),
        (StateColumnType::String, _) => Err(StateSqlError(STRING_VALUE_REQUIRED.to_owned())),
        (StateColumnType::TextTimestamp, StateValue::UtcTimestamp(local)) => {
            Ok(quoted(&utc_isoformat(local)))
        }
        (StateColumnType::TextTimestamp, _) => {
            Err(StateSqlError(TIMESTAMP_VALUE_REQUIRED.to_owned()))
        }
    }
}
