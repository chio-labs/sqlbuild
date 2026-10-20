//! Python's text of a plain scalar config value.

use crate::config_values::_helpers::reprs::scalar_text;
use crate::config_values::models::ConfigNode;

/// Python's exact `str()` (or `repr()`) of `None`, a boolean, an integer, a float or a string's `str()`; else `None`.
#[must_use]
pub fn plain_scalar_text<H>(value: &ConfigNode<H>, repr: bool) -> Option<String> {
    scalar_text(value, repr)
}
