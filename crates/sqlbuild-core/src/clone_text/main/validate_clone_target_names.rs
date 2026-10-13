//! Check that clone origin and destination name distinct, known targets.

use std::collections::BTreeSet;

use crate::clone_text::errors::CloneTargetError;

/// C401 for the same target, C402 for an unknown origin, C403 for an unknown destination.
pub fn validate_clone_target_names(
    (origin, destination): (&str, &str),
    known: &BTreeSet<String>,
) -> Result<(), CloneTargetError> {
    if origin == destination {
        return Err(CloneTargetError {
            code: "C401",
            message: "clone requires different --from and --to targets".to_owned(),
        });
    }
    if !known.contains(origin) {
        return Err(CloneTargetError {
            code: "C402",
            message: format!("unknown target '{origin}'"),
        });
    }
    if !known.contains(destination) {
        return Err(CloneTargetError {
            code: "C403",
            message: format!("unknown target '{destination}'"),
        });
    }
    Ok(())
}
