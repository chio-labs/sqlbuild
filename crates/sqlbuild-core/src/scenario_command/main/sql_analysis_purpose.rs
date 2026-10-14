//! The purpose SQL analysis guidance names for a scenario command.

use crate::scenario_command::models::SqlAnalysisCommand;

/// The purpose a config file's SQL analysis guidance names for `command`.
#[must_use]
pub fn sql_analysis_purpose(command: SqlAnalysisCommand) -> &'static str {
    match command {
        SqlAnalysisCommand::LocalTest => {
            "to run local scenario replay, snapshot sync, or snapshot refresh"
        }
        SqlAnalysisCommand::Capture => "to capture snapshots for local scenario replay",
    }
}
