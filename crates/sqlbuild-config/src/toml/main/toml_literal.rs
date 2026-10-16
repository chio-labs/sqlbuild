//! A TOML literal as SQLBuild writes it into configuration text and help.

use crate::toml::models::TomlLiteral;

/// `true`/`false`, the integer digits, a `"`-quoted string escaping `\` and `"`, or `[a, b]`.
#[must_use]
pub fn toml_literal(value: &TomlLiteral) -> String {
    match value {
        TomlLiteral::Bool(true) => "true".to_owned(),
        TomlLiteral::Bool(false) => "false".to_owned(),
        TomlLiteral::Integer(digits) => digits.clone(),
        TomlLiteral::Text(text) => {
            format!("\"{}\"", text.replace('\\', "\\\\").replace('"', "\\\""))
        }
        TomlLiteral::Array(items) => {
            let items: Vec<String> = items.iter().map(toml_literal).collect();
            format!("[{}]", items.join(", "))
        }
    }
}
