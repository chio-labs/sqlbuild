//! `short_invocation_id`: the prefix of an invocation ID that output shows.

use crate::command_output::constants::SHORT_INVOCATION_ID_LENGTH;

/// The first [`SHORT_INVOCATION_ID_LENGTH`] characters of `invocation_id`, or all of a shorter one.
#[must_use]
pub fn short_invocation_id(invocation_id: &str) -> &str {
    invocation_id
        .char_indices()
        .nth(SHORT_INVOCATION_ID_LENGTH)
        .map_or(invocation_id, |(end, _)| &invocation_id[..end])
}
