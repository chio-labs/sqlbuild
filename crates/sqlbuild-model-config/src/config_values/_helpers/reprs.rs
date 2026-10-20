//! Python's `str()` and `repr()` of config values: plain scalars in Rust, the rest by Python.

use sqlbuild_core::json::main::python_float_repr::python_float_repr;

use crate::config_values::constants::{FALSE_TEXT, NONE_TEXT, TRUE_TEXT};
use crate::config_values::models::ConfigNode;
use crate::config_values::types::HostObject;

/// Python's exact `str()` (or `repr()`) of a plain scalar, or `None` for any other value.
pub(crate) fn scalar_text<H>(value: &ConfigNode<H>, repr: bool) -> Option<String> {
    match value {
        ConfigNode::Null => Some(NONE_TEXT.to_owned()),
        ConfigNode::Bool(true) => Some(TRUE_TEXT.to_owned()),
        ConfigNode::Bool(false) => Some(FALSE_TEXT.to_owned()),
        ConfigNode::Int(number) => Some(number.to_string()),
        ConfigNode::Float(number) => Some(python_float_repr(*number)),
        ConfigNode::Str(text) if !repr => Some(text.clone()),
        _ => None,
    }
}

/// Python's `repr(value)`.
pub(crate) fn python_repr<H: HostObject>(value: &ConfigNode<H>) -> String {
    scalar_text(value, true).unwrap_or_else(|| H::display(value, true))
}

/// Python's `str(value)`.
pub(crate) fn python_str<H: HostObject>(value: &ConfigNode<H>) -> String {
    scalar_text(value, false).unwrap_or_else(|| H::display(value, false))
}
