//! The error when an adapter has no SQL analysis dialect for scenario snapshots.

use crate::scenario_command::constants::CAPTURE_DIALECT_REQUIRED_CODE;
use crate::scenario_command::errors::ScenarioCommandError;

/// Snapshots need the adapter's SQL analysis dialect to be validated and replayed.
#[must_use]
pub fn capture_dialect_required_error(adapter_name: &str) -> ScenarioCommandError {
    ScenarioCommandError {
        code: CAPTURE_DIALECT_REQUIRED_CODE,
        message: format!(
            "Adapter '{adapter_name}' must define a SQL analysis dialect for scenario snapshots"
        ),
        help: Some(
            "Set sql_analysis_dialect_name on the adapter so captured snapshots can be validated \
             and replayed locally."
                .to_owned(),
        ),
    }
}
