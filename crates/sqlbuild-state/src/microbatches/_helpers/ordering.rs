//! Cursor bound comparisons and stable sorts by bound key.

use std::cmp::Ordering;

use sqlbuild_cursor::algebra::models::SortKey;

use crate::microbatches::models::CursorBound;

/// How two keys of one cursor type order; integers and moments never meet in one history.
pub(crate) fn key_cmp(left: &SortKey, right: &SortKey) -> Ordering {
    match (left, right) {
        (SortKey::Integer(left), SortKey::Integer(right)) => left.cmp(right),
        (SortKey::Moment(left), SortKey::Moment(right)) => left.cmp(right),
        (SortKey::Integer(_), SortKey::Moment(_)) => Ordering::Less,
        (SortKey::Moment(_), SortKey::Integer(_)) => Ordering::Greater,
    }
}

pub(crate) fn lt(left: &CursorBound, right: &CursorBound) -> bool {
    key_cmp(&left.key, &right.key) == Ordering::Less
}

pub(crate) fn lte(left: &CursorBound, right: &CursorBound) -> bool {
    key_cmp(&left.key, &right.key) != Ordering::Greater
}

/// `items` stably sorted by the key `bound` selects.
pub(crate) fn sorted_by_bound<T: Clone>(items: &[T], bound: impl Fn(&T) -> &CursorBound) -> Vec<T> {
    let mut sorted: Vec<T> = items.to_vec();
    sorted.sort_by(|left, right| key_cmp(&bound(left).key, &bound(right).key));
    sorted
}

/// The first non-empty bound holding the smallest (`wanted = Less`) or largest key.
pub(crate) fn extreme<'a>(
    bounds: impl Iterator<Item = &'a CursorBound>,
    wanted: Ordering,
) -> Option<&'a CursorBound> {
    let mut best: Option<&CursorBound> = None;
    for bound in bounds.filter(|bound| !bound.text.is_empty()) {
        match best {
            Some(current) if key_cmp(&bound.key, &current.key) != wanted => {}
            _ => best = Some(bound),
        }
    }
    best
}
