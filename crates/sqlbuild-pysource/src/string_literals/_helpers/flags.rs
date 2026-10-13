//! Whether one string constant names a renamed model or column.

use sqlbuild_core::text::main::python_strip::python_strip;

use crate::string_literals::_helpers::python_re::{has_word, python_lower, sql_like};
use crate::string_literals::models::StringQuery;

/// A name equal to the stripped string, or a whole word of SQL-like text; a context must appear too.
pub(crate) fn flags(value: &str, query: &StringQuery<'_>) -> bool {
    let text: Vec<char> = value.chars().collect();
    let is_sql_like: bool = sql_like(&text);
    if let Some(context) = query.context
        && !(is_sql_like && has_word(&text, context))
    {
        return false;
    }
    let stripped: String = python_lower(python_strip(value));
    query
        .names
        .iter()
        .any(|name| stripped == python_lower(name) || (is_sql_like && has_word(&text, name)))
}
