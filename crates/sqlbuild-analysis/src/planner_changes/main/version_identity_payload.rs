//! The fingerprint metadata that participates in version identity.

use crate::planner_changes::_helpers::json_payload::decoded_object;
use crate::planner_changes::constants::{
    AUDIT_GATE_METADATA_KEY, DECLARED_COLUMNS_METADATA_KEY, LOCAL_FUNCTION_HASHES_METADATA_KEY,
    MIGRATION_FINGERPRINT_METADATA_KEY,
};
use crate::planner_changes::models::IdentityPayload;

/// The metadata without audit-gate, migration and declared-column entries; with `without_functions`, also without function hashes.
pub fn version_identity_payload(
    metadata_json: Option<&str>,
    without_functions: bool,
) -> IdentityPayload {
    let Some(text) = metadata_json else {
        return IdentityPayload::Absent;
    };
    match decoded_object(text) {
        Err(()) => IdentityPayload::Raw(text.to_owned()),
        Ok(None) => IdentityPayload::Absent,
        Ok(Some(mut object)) => {
            for key in [
                AUDIT_GATE_METADATA_KEY,
                MIGRATION_FINGERPRINT_METADATA_KEY,
                DECLARED_COLUMNS_METADATA_KEY,
            ] {
                object.shift_remove(key);
            }
            if without_functions {
                object.shift_remove(LOCAL_FUNCTION_HASHES_METADATA_KEY);
            }
            IdentityPayload::Object(object)
        }
    }
}
