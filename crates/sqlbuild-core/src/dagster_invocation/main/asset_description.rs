//! The default Dagster description: the node's text followed by its SQL or source file.

use crate::dagster_invocation::_helpers::markdown::markdown_code_span;
use crate::text::main::python_strip::python_strip;

/// `description` followed by its stripped SQL block, or else by its source file code span.
#[must_use]
pub fn asset_description(description: &str, sql: Option<&str>, path: Option<&str>) -> String {
    if let Some(sql) = sql.map(python_strip).filter(|sql| !sql.is_empty()) {
        return format!("{description}\n\n**SQLBuild SQL:**\n```sql\n{sql}\n```");
    }
    if let Some(path) = path.filter(|path| !path.is_empty()) {
        return format!(
            "{description}\n\n**Source file:** {}",
            markdown_code_span(path)
        );
    }
    description.to_owned()
}
