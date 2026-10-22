//! `render_script`: statements as one script an administrator runs.

/// `statements` as one script, each terminated by `;`.
#[must_use]
pub fn render_script(statements: &[String]) -> String {
    let mut script: String = statements.join(";\n\n");
    script.push_str(";\n");
    script
}
