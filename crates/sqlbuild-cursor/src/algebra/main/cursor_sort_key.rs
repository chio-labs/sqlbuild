//! `cursor_sort_key`: the sortable projection of one cursor value.

use crate::algebra::_helpers::comparison::sort_key;
use crate::algebra::errors::CursorError;
use crate::algebra::models::{Scalar, SortKey};
use crate::algebra::types::ZoneRules;

/// The integer, or the naive UTC wall time, `value` sorts by.
pub fn cursor_sort_key(value: &Scalar, rules: &dyn ZoneRules) -> Result<SortKey, CursorError> {
    sort_key(value, rules)
}
