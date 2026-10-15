//! Case-insensitive relation identity, treating an unknown database as a wildcard.

use crate::events::models::EventRelation;

/// `MigrationRelation.matches`: equal schema and name, and databases equal unless one is unknown.
pub(crate) fn relations_match(left: &EventRelation, right: &EventRelation) -> bool {
    let schema = |relation: &EventRelation| -> String {
        relation
            .schema
            .as_deref()
            .unwrap_or_default()
            .to_lowercase()
    };
    if schema(left) != schema(right) || left.name.to_lowercase() != right.name.to_lowercase() {
        return false;
    }
    match (&left.database, &right.database) {
        (Some(left), Some(right)) => left.to_lowercase() == right.to_lowercase(),
        _ => true,
    }
}

/// The index of the greatest order among the selected items, keeping the first of equal ones.
pub(crate) fn newest_index<'a, T: Ord + 'a>(
    orders: impl Iterator<Item = (usize, &'a T)>,
) -> Option<usize> {
    let mut newest: Option<(usize, &T)> = None;
    for (index, order) in orders {
        if newest.is_none_or(|(_, current)| order > current) {
            newest = Some((index, order));
        }
    }
    newest.map(|(index, _)| index)
}
