//! `event_cursor_position`: the storage position an event cursor names.

use crate::execution_history::_helpers::dialects::event_cursor_prefix;
use crate::execution_history::constants::{
    CURSOR_SEPARATOR, FIRST_POSITION, FOREIGN_EVENT_CURSOR, MALFORMED_EVENT_CURSOR,
};
use crate::execution_history::errors::{HistoryError, HistoryErrorKind};
use crate::execution_history::models::Dialect;

/// Position zero without a cursor, else the positive position of this storage's cursor.
pub fn event_cursor_position(
    dialect: Dialect,
    cursor: Option<&str>,
    namespace: &str,
) -> Result<i64, HistoryError> {
    let Some(cursor) = cursor else {
        return Ok(0);
    };
    let malformed = || HistoryError::new(HistoryErrorKind::InvalidCursor, MALFORMED_EVENT_CURSOR);
    let mut parts = cursor.rsplitn(3, CURSOR_SEPARATOR);
    let (Some(raw_position), Some(cursor_namespace), Some(prefix)) =
        (parts.next(), parts.next(), parts.next())
    else {
        return Err(malformed());
    };
    let position: i64 = raw_position.trim().parse().map_err(|_| malformed())?;
    let expected_prefix: &str = event_cursor_prefix(dialect);
    let prefix_matches: bool = expected_prefix.strip_suffix(CURSOR_SEPARATOR) == Some(prefix);
    if !prefix_matches || cursor_namespace != namespace || position < FIRST_POSITION {
        return Err(HistoryError::new(
            HistoryErrorKind::InvalidCursor,
            FOREIGN_EVENT_CURSOR,
        ));
    }
    Ok(position)
}
