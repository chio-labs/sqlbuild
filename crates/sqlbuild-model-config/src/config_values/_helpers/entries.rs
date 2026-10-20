//! A config mapping read and written as a Python `dict`.

use crate::config_values::models::ConfigNode;
use crate::config_values::types::HostObject;
use crate::types::{AuthoredNode, NodeKind};

/// The exact text of a string key, borrowed.
fn key_text<H>(node: &ConfigNode<H>) -> Option<&str> {
    match node {
        ConfigNode::Str(text) => Some(text),
        ConfigNode::Host(host) if host.facts.kind == NodeKind::Str && host.facts.strict_text => {
            host.facts.text.as_deref()
        }
        _ => None,
    }
}

/// Python's `==` between two dict keys: equal text, equal numbers, or equal tuples.
pub(crate) fn same_key<H: HostObject>(left: &ConfigNode<H>, right: &ConfigNode<H>) -> bool {
    match (left, right) {
        (ConfigNode::Null, ConfigNode::Null) => true,
        (ConfigNode::Tuple(left), ConfigNode::Tuple(right)) => {
            left.len() == right.len() && left.iter().zip(right).all(|(a, b)| same_key(a, b))
        }
        _ => match (key_text(left), key_text(right)) {
            (Some(left), Some(right)) => left == right,
            (None, None) => match (numeric(left), numeric(right)) {
                (Some(left), Some(right)) => left == right,
                _ => false,
            },
            _ => false,
        },
    }
}

/// A boolean, integer or float key's numeric value, as Python compares keys.
fn numeric<H: HostObject>(node: &ConfigNode<H>) -> Option<f64> {
    match node {
        ConfigNode::Bool(flag) => Some(f64::from(u8::from(*flag))),
        ConfigNode::Int(_) | ConfigNode::Float(_) => node.number(),
        _ => None,
    }
}

/// `mapping.get(key)` for a string key.
pub(crate) fn entry<'a, H: HostObject>(
    entries: &'a [(ConfigNode<H>, ConfigNode<H>)],
    key: &str,
) -> Option<&'a ConfigNode<H>> {
    entries
        .iter()
        .find(|(name, _)| key_text(name) == Some(key))
        .map(|(_, value)| value)
}

/// `mapping.get(key)` unless absent or `None`.
pub(crate) fn set_entry<'a, H: HostObject>(
    entries: &'a [(ConfigNode<H>, ConfigNode<H>)],
    key: &str,
) -> Option<&'a ConfigNode<H>> {
    entry(entries, key).filter(|value| !matches!(value, ConfigNode::Null))
}

/// `entries` after `mapping[key] = value`: an equal key keeps its place and its key, else the entry is appended.
pub(crate) fn inserted<H: HostObject>(
    mut entries: Vec<(ConfigNode<H>, ConfigNode<H>)>,
    key: ConfigNode<H>,
    value: ConfigNode<H>,
) -> Vec<(ConfigNode<H>, ConfigNode<H>)> {
    match entries.iter().position(|(name, _)| same_key(name, &key)) {
        Some(position) => entries[position].1 = value,
        None => entries.push((key, value)),
    }
    entries
}
