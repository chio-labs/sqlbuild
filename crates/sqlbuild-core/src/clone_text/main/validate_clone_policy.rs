//! Check that the targets' clone policies allow the requested direction.

use crate::clone_text::errors::CloneTargetError;

/// C404 when the origin may not be cloned from, C405 when the destination may not be cloned to.
pub fn validate_clone_policy(
    (origin, destination): (&str, &str),
    (origin_allowed, destination_allowed): (bool, bool),
) -> Result<(), CloneTargetError> {
    if !origin_allowed {
        return Err(CloneTargetError {
            code: "C404",
            message: format!(
                "target '{origin}' is not allowed as a clone origin target; \
                 set targets.{origin}.clone.allow_as_clone_origin = true"
            ),
        });
    }
    if !destination_allowed {
        return Err(CloneTargetError {
            code: "C405",
            message: format!(
                "target '{destination}' is not allowed as a clone destination target; \
                 set targets.{destination}.clone.allow_as_clone_destination = true"
            ),
        });
    }
    Ok(())
}
