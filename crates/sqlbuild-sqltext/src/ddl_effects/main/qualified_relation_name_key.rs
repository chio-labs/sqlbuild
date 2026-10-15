//! The cache invalidation key of a qualified relation name's last part.

use crate::ddl_effects::_helpers::matching::{only_whitespace, skip_whitespace};
use crate::ddl_effects::_helpers::names::{UnquotedPart, part_name_key, qualified_name};

/// The key for the last part of a qualified name, or `None` when it cannot be parsed.
#[must_use]
pub fn qualified_relation_name_key(qualified: &str) -> Option<String> {
    let name = qualified_name(
        qualified,
        skip_whitespace(qualified, 0),
        UnquotedPart::Loose,
    )?;
    only_whitespace(qualified, name.end).then(|| part_name_key(name.last_part))
}
