//! Resource identifier resolution shared by terminal lookups.

use crate::terminal_events::models::TerminalIndex;

/// The given identifier, else the only identifier seen for the resource name.
pub(crate) fn resolved_resource_id(
    index: &TerminalIndex,
    resource_name: &str,
    resource_id: Option<&str>,
) -> Option<String> {
    if let Some(resource_id) = resource_id.filter(|resource_id| !resource_id.is_empty()) {
        return Some(resource_id.to_owned());
    }
    match index
        .resource_ids_by_name
        .get(resource_name)
        .map(Vec::as_slice)
    {
        Some([only]) => Some(only.clone()),
        _ => None,
    }
}
