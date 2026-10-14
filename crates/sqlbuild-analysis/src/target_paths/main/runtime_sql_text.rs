//! The text of a runtime SQL artifact: its statements, each terminated.

use sqlbuild_core::text::main::python_isspace::python_isspace;

/// The statements joined by blank lines, each ending in `;`, with one final newline.
#[must_use]
pub fn runtime_sql_text(statements: &[String]) -> String {
    let joined: String = statements
        .iter()
        .map(|statement| {
            let stripped: &str = statement.trim_end_matches(python_isspace);
            if stripped.is_empty() {
                statement.clone()
            } else if stripped.ends_with(';') {
                stripped.to_owned()
            } else {
                format!("{stripped};")
            }
        })
        .collect::<Vec<String>>()
        .join("\n\n");
    format!("{}\n", joined.trim_end_matches(python_isspace))
}
