//! The relation and CTE a `SQBRSQL038` finding names, for relation-level Rule exceptions.

use crate::sql_lint::constants::{CROSS_JOIN_CTE_MARKER, CROSS_JOIN_PREFIX, CROSS_JOIN_SUFFIX};

/// The `(relation, cte)` a cross join finding message names, `None` for the generic message.
#[must_use]
pub fn cross_join_subject(message: &str) -> Option<(String, Option<String>)> {
    let named: &str = message
        .strip_prefix(CROSS_JOIN_PREFIX)?
        .strip_suffix(CROSS_JOIN_SUFFIX)?;
    match named.split_once(CROSS_JOIN_CTE_MARKER) {
        Some((relation, cte)) => Some((relation.to_owned(), Some(cte.to_owned()))),
        None => Some((named.to_owned(), None)),
    }
}
