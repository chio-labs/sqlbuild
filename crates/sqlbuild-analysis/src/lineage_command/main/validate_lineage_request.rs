//! The combinations of targets, `--select` and `--exclude` `sqb lineage` accepts.

use crate::lineage_command::constants::COLUMN_TARGET_SEPARATOR;
use crate::lineage_command::errors::LineageError;
use crate::lineage_command::models::LineageRequestShape;

/// Reject conflicting or missing target and selector options.
pub fn validate_lineage_request(request: &LineageRequestShape) -> Result<(), LineageError> {
    if !request.targets.is_empty() && !request.select.is_empty() {
        return Err(LineageError::new(
            "C301",
            "lineage accepts either targets or --select, not both",
        ));
    }
    if request.targets.is_empty() && request.select.is_empty() {
        return Err(LineageError::new(
            "C302",
            "lineage requires a target or --select",
        ));
    }
    if request.targets.len() > 1
        && request
            .targets
            .iter()
            .any(|target| target.contains(COLUMN_TARGET_SEPARATOR))
    {
        return Err(LineageError::new(
            "C320",
            "column lineage accepts exactly one model.column target",
        )
        .with_help("run one lineage command per column"));
    }
    if !request.exclude.is_empty() && request.select.is_empty() {
        return Err(LineageError::new(
            "C303",
            "--exclude can only be used with --select",
        ));
    }
    Ok(())
}
