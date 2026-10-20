//! Python's `str()` and `repr()` of config values.

use sqlbuild_core::json::main::python_float_repr::python_float_repr;
use sqlbuild_core::text::main::python_str_repr::python_str_repr;

use crate::config_values::constants::{FALSE_TEXT, NONE_TEXT, TRUE_TEXT};
use crate::config_values::models::ConfigNode;

fn joined<H>(items: &[ConfigNode<H>]) -> String {
    items.iter().map(python_repr).collect::<Vec<_>>().join(", ")
}

/// Python's `repr(value)`.
pub(crate) fn python_repr<H>(value: &ConfigNode<H>) -> String {
    match value {
        ConfigNode::Null => NONE_TEXT.to_owned(),
        ConfigNode::Bool(true) => TRUE_TEXT.to_owned(),
        ConfigNode::Bool(false) => FALSE_TEXT.to_owned(),
        ConfigNode::Int(number) => number.to_string(),
        ConfigNode::Float(number) => python_float_repr(*number),
        ConfigNode::Str(text) => python_str_repr(text),
        ConfigNode::List(items) => format!("[{}]", joined(items)),
        ConfigNode::Tuple(items) if items.len() == 1 => format!("({},)", joined(items)),
        ConfigNode::Tuple(items) => format!("({})", joined(items)),
        ConfigNode::Map(entries) => format!(
            "{{{}}}",
            entries
                .iter()
                .map(|(key, item)| format!("{}: {}", python_repr(key), python_repr(item)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
        ConfigNode::Host(host) => host.facts.python_repr.clone(),
    }
}

/// Python's `str(value)`: a string's own text, an opaque value's `str()`, else its `repr()`.
pub(crate) fn python_str<H>(value: &ConfigNode<H>) -> String {
    match value {
        ConfigNode::Str(text) => text.clone(),
        ConfigNode::Host(host) => host.facts.python_str.clone(),
        _ => python_repr(value),
    }
}
