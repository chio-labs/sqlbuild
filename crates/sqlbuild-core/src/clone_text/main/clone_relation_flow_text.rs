//! The plain origin-to-destination text of one clone item.

use crate::clone_text::_helpers::quoted::clone_relation_display_name;

/// `origin -> destination`, or the lowercased name when either relation is unknown.
#[must_use]
pub fn clone_relation_flow_text(
    name: &str,
    (origin, destination): (Option<&str>, Option<&str>),
) -> String {
    match (origin, destination) {
        (Some(origin), Some(destination)) => format!(
            "{} -> {}",
            clone_relation_display_name(origin),
            clone_relation_display_name(destination)
        ),
        _ => name.to_lowercase(),
    }
}
