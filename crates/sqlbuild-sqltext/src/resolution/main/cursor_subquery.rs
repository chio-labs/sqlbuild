//! Shared cursor-filtered relation construction.

use crate::resolution::models::CursorFilter;

/// Wrap an adapter-rendered relation and bounds in a cursor filter.
pub fn cursor_subquery(relation: &str, filter: &CursorFilter<'_>, alias: bool) -> String {
    let lower = if filter.lower_inclusive { ">=" } else { ">" };
    let upper = if filter.typed { "<" } else { "<=" };
    let suffix = if alias { " AS __cursor_ref" } else { "" };
    format!(
        "(SELECT * FROM {relation} WHERE {} {lower} {} AND {} {upper} {}){suffix}",
        filter.column, filter.start, filter.column, filter.end
    )
}
