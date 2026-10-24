//! The digest of a SQL macro file's definition, with formatting, comments and description ignored.

use crate::definition_changes::_helpers::sql_macro_parts::{parameter_text, type_text};
use crate::definition_changes::main::definition_digest::definition_digest;
use crate::definition_changes::main::sql_definition_digest::sql_definition_digest;
use crate::sql_macros::main::parse_sql_macro::parse_sql_macro;

/// The digest of SQL macro `name`'s form, arguments, result type and body; its tokens if invalid.
pub fn sql_macro_definition_digest(name: &str, path: &str, source: &str) -> String {
    let Ok(definition) = parse_sql_macro(name, path, source) else {
        return sql_definition_digest(source);
    };
    let mut parts: Vec<String> = vec![
        definition.form.label().to_owned(),
        match (&definition.returns, &definition.returns_like) {
            (Some(returns), _) => type_text(returns),
            (None, Some(like)) => format!("type of {}", like.to_lowercase()),
            (None, None) => String::new(),
        },
        sql_definition_digest(&definition.body),
    ];
    for parameter in &definition.parameters {
        parts.push(parameter_text(parameter));
    }
    let borrowed: Vec<&str> = parts.iter().map(String::as_str).collect();
    definition_digest(&borrowed)
}
