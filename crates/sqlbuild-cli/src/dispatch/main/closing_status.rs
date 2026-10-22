//! The closing line after an incomplete-delivery notice, so the command's own outcome is the last word.

/// `sqb <command>`'s outcome by exit code, naming the only thing a preceding notice affects; with nothing `affected`, as after a purely informational notice, success is reported plainly.
#[must_use]
pub fn closing_status(command: &str, exit_code: Option<i64>, affected: Option<&str>) -> String {
    match (exit_code, affected) {
        (Some(0), Some(affected)) => {
            format!("sqb {command} completed successfully; only its {affected} is affected.\n")
        }
        (Some(0), None) => format!("sqb {command} completed successfully.\n"),
        (Some(code), _) => format!("sqb {command} failed with exit code {code}.\n"),
        (None, _) => format!("sqb {command} failed.\n"),
    }
}
