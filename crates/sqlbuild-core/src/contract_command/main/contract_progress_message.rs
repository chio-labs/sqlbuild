//! Lifecycle messages of contract inspection and repository updates.

use crate::contract_command::models::ContractProgress;

fn counted(count: usize, singular: &str) -> String {
    format!("{count} {singular}{}", if count == 1 { "" } else { "s" })
}

/// The status line text of one contract lifecycle event.
#[must_use]
pub fn contract_progress_message(event: &ContractProgress) -> String {
    match event {
        ContractProgress::InspectionStart { count, target } => format!(
            "Inspecting {} from target '{target}'...",
            counted(*count, "contract")
        ),
        ContractProgress::InspectionComplete {
            count,
            target,
            seconds,
        } => format!(
            "Inspected {} from target '{target}' ({seconds:.2}s)",
            counted(*count, "contract")
        ),
        ContractProgress::InspectionFailed { seconds } => {
            format!("Contract inspection failed after {seconds:.2}s")
        }
        ContractProgress::WriteComplete { count, seconds } => format!(
            "Updated repository contracts ({}, {seconds:.2}s)",
            counted(*count, "file")
        ),
        ContractProgress::WriteFailed { seconds } => {
            format!("Repository contract update failed after {seconds:.2}s")
        }
    }
}
