//! Relation names the janitor can address without quoting.

use std::collections::HashSet;

use crate::janitor_planning::constants::UNQUOTED_ADDRESSING_REASON;
use crate::janitor_planning::main::case_collision_reason::case_collision_reason;

/// Why the janitor must not rename or drop a relation by its catalog name, if it must not.
#[must_use]
pub fn unaddressable_relation_reason(
    name: &str,
    colliding_names: &HashSet<String>,
) -> Option<&'static str> {
    if !plain_lowercase_identifier(name) {
        return Some(UNQUOTED_ADDRESSING_REASON);
    }
    case_collision_reason(name, colliding_names)
}

fn plain_lowercase_identifier(name: &str) -> bool {
    let mut characters = name.chars();
    characters
        .next()
        .is_some_and(|first| first.is_ascii_lowercase() || first == '_')
        && characters.all(|character| {
            character.is_ascii_lowercase()
                || character.is_ascii_digit()
                || character == '_'
                || character == '$'
        })
}
