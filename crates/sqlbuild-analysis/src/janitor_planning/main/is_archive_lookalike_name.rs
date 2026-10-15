//! Names reserved for janitor archive handling.

use crate::janitor_planning::constants::ARCHIVE_LOOKALIKE_PREFIX;

/// Whether a relation name starts, ignoring case, with the archive prefix.
#[must_use]
pub fn is_archive_lookalike_name(name: &str) -> bool {
    name.to_lowercase().starts_with(ARCHIVE_LOOKALIKE_PREFIX)
}
