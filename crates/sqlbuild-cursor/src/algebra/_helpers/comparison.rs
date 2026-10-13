//! Cursor values projected into one sortable domain and compared there.

use std::cmp::Ordering;

use crate::algebra::_helpers::civil::{add_micros, midnight};
use crate::algebra::_helpers::failures::algebra;
use crate::algebra::constants::{INTEGER_KEY_TYPE, MIXED_COMPARISON, MOMENT_KEY_TYPE};
use crate::algebra::errors::CursorError;
use crate::algebra::models::{Scalar, ScalarValue, SortKey, ZoneOffset};
use crate::algebra::types::ZoneRules;

/// An integer, a date's midnight, or a timestamp's naive UTC wall time.
pub(crate) fn sort_key(value: &Scalar, rules: &dyn ZoneRules) -> Result<SortKey, CursorError> {
    Ok(match &value.value {
        ScalarValue::Integer(number) => SortKey::Integer(*number),
        ScalarValue::Date(date) => SortKey::Moment(midnight(*date)),
        ScalarValue::Timestamp(timestamp) => SortKey::Moment(match timestamp.offset {
            ZoneOffset::Naive => timestamp.local,
            ZoneOffset::Fixed(offset) => add_micros(&timestamp.local, -i128::from(offset))?,
            ZoneOffset::External(template) => {
                rules.to_utc(template, &timestamp.local, timestamp.fold)?
            }
        }),
    })
}

/// The ordering of two keys of one kind, or `None` across kinds.
pub(crate) fn key_ordering(left: &SortKey, right: &SortKey) -> Option<Ordering> {
    match (left, right) {
        (SortKey::Integer(left), SortKey::Integer(right)) => Some(left.cmp(right)),
        (SortKey::Moment(left), SortKey::Moment(right)) => Some(left.cmp(right)),
        _ => None,
    }
}

/// The Python type name of a key, as a failed rich comparison reports it.
pub(crate) fn key_type(key: &SortKey) -> &'static str {
    match key {
        SortKey::Integer(_) => INTEGER_KEY_TYPE,
        SortKey::Moment(_) => MOMENT_KEY_TYPE,
    }
}

/// `TypeError` for `left <operator> right` across key kinds.
pub(crate) fn unorderable(operator: &str, left: &SortKey, right: &SortKey) -> CursorError {
    CursorError::Type(format!(
        "'{operator}' not supported between instances of '{}' and '{}'",
        key_type(left),
        key_type(right)
    ))
}

/// The ordering of two compatible cursor values.
pub(crate) fn compare_scalars(
    left: &Scalar,
    right: &Scalar,
    rules: &dyn ZoneRules,
) -> Result<Ordering, CursorError> {
    let left_key: SortKey = sort_key(left, rules)?;
    let right_key: SortKey = sort_key(right, rules)?;
    key_ordering(&left_key, &right_key).ok_or_else(|| algebra(MIXED_COMPARISON))
}
