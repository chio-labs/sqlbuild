//! Compare current and recorded version-identity metadata.

use crate::planner_changes::_helpers::function_hashes::{
    changed_local_function_names, payloads_equal,
};
use crate::planner_changes::_helpers::with_origin_cursor_input_names::with_origin_cursor_input_names;
use crate::planner_changes::main::version_identity_payload::version_identity_payload;
use crate::planner_changes::models::MetadataChanges;

/// Called functions whose recorded hash changed (when queries are tracked) and whether the remaining identity changed.
pub fn metadata_changes(
    (metadata_json, recorded_metadata_json): (&str, Option<&str>),
    origin_names: Option<&[(String, String)]>,
    query_change_tracking: bool,
) -> MetadataChanges {
    let Some(recorded) = recorded_metadata_json else {
        return MetadataChanges::default();
    };
    let changed_functions: Vec<String> = if query_change_tracking {
        changed_local_function_names(metadata_json, recorded)
    } else {
        Vec::new()
    };
    let current: String = match origin_names {
        Some(names) => with_origin_cursor_input_names(metadata_json, names),
        None => metadata_json.to_owned(),
    };
    let without_functions: bool = !changed_functions.is_empty();
    let config_changed: bool = !payloads_equal(
        &version_identity_payload(Some(&current), without_functions),
        &version_identity_payload(Some(recorded), without_functions),
    );
    MetadataChanges {
        changed_functions,
        config_changed,
    }
}
