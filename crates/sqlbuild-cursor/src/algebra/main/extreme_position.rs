//! `extreme_position`: which key `max()` or `min()` selects.

use std::cmp::Ordering;

use crate::algebra::_helpers::comparison::{key_ordering, unorderable};
use crate::algebra::errors::CursorError;
use crate::algebra::models::{Extreme, SortKey};

/// The first position holding the largest or smallest key, failing as `max`/`min` fail.
pub fn extreme_position(keys: &[SortKey], extreme: Extreme) -> Result<usize, CursorError> {
    let (operator, wanted, name): (&str, Ordering, &str) = match extreme {
        Extreme::Max => (">", Ordering::Greater, "max"),
        Extreme::Min => ("<", Ordering::Less, "min"),
    };
    let Some(first) = keys.first() else {
        return Err(CursorError::Value(format!(
            "{name}() iterable argument is empty"
        )));
    };
    let mut best: (usize, &SortKey) = (0, first);
    for (index, key) in keys.iter().enumerate().skip(1) {
        let Some(ordering) = key_ordering(key, best.1) else {
            return Err(unorderable(operator, key, best.1));
        };
        if ordering == wanted {
            best = (index, key);
        }
    }
    Ok(best.0)
}
