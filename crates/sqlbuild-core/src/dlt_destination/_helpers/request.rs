//! Destination config and dataset rules checked before any adapter credentials.

use crate::dlt_destination::constants::SQLBUILD_OWNED_DESTINATION_KEYS;
use crate::dlt_destination::errors::DltDestinationError;
use crate::dlt_destination::models::DltDatasetName;
use crate::text::main::python_strip::python_strip;

/// Reject a destination config that sets keys SQLBuild owns.
pub(crate) fn check_destination_keys(
    adapter: &str,
    destination_keys: &[Option<String>],
) -> Result<(), DltDestinationError> {
    let mut blocked: Vec<&str> = destination_keys
        .iter()
        .flatten()
        .map(String::as_str)
        .filter(|key| SQLBUILD_OWNED_DESTINATION_KEYS.contains(key))
        .collect();
    if blocked.is_empty() {
        return Ok(());
    }
    blocked.sort_unstable();
    Err(DltDestinationError {
        message: format!(
            "Adapter '{adapter}' dlt destination config cannot define SQLBuild-owned key(s): {}",
            blocked.join(", ")
        ),
    })
}

/// Reject a missing or blank dataset name, which raw landing requires.
pub(crate) fn check_dataset_name(
    adapter: &str,
    dataset_name: &DltDatasetName,
) -> Result<(), DltDestinationError> {
    let named: bool = dataset_name
        .text
        .as_deref()
        .is_some_and(|name| !python_strip(name).is_empty());
    if named {
        return Ok(());
    }
    Err(DltDestinationError {
        message: format!(
            "Adapter '{adapter}' requires an explicit dlt source schema for raw landing"
        ),
    })
}
