//! The closing line after an incomplete-delivery notice, so the command's own outcome is the last word.

/// `sqb <command>`'s outcome by exit code, naming the only thing a preceding notice affects.
#[must_use]
pub fn closing_status(command: &str, exit_code: Option<i64>, affected: &str) -> String {
    match exit_code {
        Some(0) => {
            format!("sqb {command} completed successfully; only its {affected} is affected.\n")
        }
        Some(code) => format!("sqb {command} failed with exit code {code}.\n"),
        None => format!("sqb {command} failed.\n"),
    }
}
