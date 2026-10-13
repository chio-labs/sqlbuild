//! `sqb scenario test` flag combinations rejected before the project is read.

use crate::scenario_command::constants::{
    LOCAL_RETAIN_UNSUPPORTED_CODE, LOCAL_SNAPSHOT_FLAG_REQUIRED_CODE,
};
use crate::scenario_command::errors::ScenarioCommandError;
use crate::scenario_command::models::ScenarioTestFlags;

/// `--local` cannot retain, and snapshot sync flags need `--local`.
pub fn validate_scenario_test_flags(flags: ScenarioTestFlags) -> Result<(), ScenarioCommandError> {
    if flags.local && flags.retain {
        return Err(ScenarioCommandError {
            code: LOCAL_RETAIN_UNSUPPORTED_CODE,
            message: "scenario test --local does not support --retain".to_owned(),
            help: Some(
                "Local scenario DuckDB files are always kept under target/run/scenarios/."
                    .to_owned(),
            ),
        });
    }
    if !flags.local && (flags.sync_snapshots || flags.refresh) {
        return Err(ScenarioCommandError {
            code: LOCAL_SNAPSHOT_FLAG_REQUIRED_CODE,
            message: "scenario snapshot sync flags require --local".to_owned(),
            help: Some(
                "Use sqb scenario test --local --sync-snapshots or sqb scenario test --local \
                 --refresh."
                    .to_owned(),
            ),
        });
    }
    Ok(())
}
