//! Validate an inspection-only `--as` target.

use crate::command_connection::errors::CommandConnectionError;

/// Reject an `--as` target that no project or local config defines.
pub fn check_preview_target(
    as_target: &str,
    command_name: &str,
    configured: &[String],
) -> Result<(), CommandConnectionError> {
    if configured.iter().any(|target| target == as_target) {
        return Ok(());
    }
    let mut names: Vec<&str> = configured.iter().map(String::as_str).collect();
    names.sort_unstable();
    names.dedup();
    let listed: String = if names.is_empty() {
        "none".to_owned()
    } else {
        names.join(", ")
    };
    Err(CommandConnectionError::User {
        code: None,
        message: format!("unknown target '{as_target}' for {command_name} --as"),
        help: Some(format!("Configured targets: {listed}.")),
    })
}
