//! Python's equality between two config mapping keys.

use crate::config_values::_helpers::entries::same_key;
use crate::config_values::models::ConfigNode;

/// Whether two dict keys are equal: equal text, equal numbers, or equal tuples.
#[must_use]
pub fn same_config_key<H: Clone>(left: &ConfigNode<H>, right: &ConfigNode<H>) -> bool {
    same_key(left, right)
}
