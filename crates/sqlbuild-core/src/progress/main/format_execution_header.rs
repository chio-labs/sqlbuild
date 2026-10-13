//! The command and execution context of a progress header.

/// `command  (target: ..., concurrency: N)`.
#[must_use]
pub fn format_execution_header(command: &str, target: Option<&str>, concurrency: i64) -> String {
    let mut context_parts: Vec<String> = Vec::new();
    if let Some(target) = target {
        context_parts.push(format!("target: {target}"));
    }
    context_parts.push(format!("concurrency: {concurrency}"));
    format!("{command}  ({})", context_parts.join(", "))
}
