//! Config values read as authored values, as `PyNode` reads the Python objects they mirror.

use crate::config_values::_helpers::reprs::{python_repr, python_str};
use crate::config_values::models::{ConfigNode, HostChildren};
use crate::config_values::types::HostObject;
use crate::types::{AuthoredNode, NodeKind};

impl<'a, H: HostObject> AuthoredNode for &'a ConfigNode<H> {
    fn kind(&self) -> NodeKind {
        match *self {
            ConfigNode::Null => NodeKind::Null,
            ConfigNode::Bool(flag) => NodeKind::Bool(*flag),
            ConfigNode::Int(number) => NodeKind::Int {
                negative: *number < 0,
            },
            ConfigNode::Float(_) => NodeKind::Other,
            ConfigNode::Str(_) => NodeKind::Str,
            ConfigNode::List(_) => NodeKind::List,
            ConfigNode::Tuple(_) => NodeKind::Tuple,
            ConfigNode::Map(_) => NodeKind::Map,
            ConfigNode::Host(host) => host.facts.kind,
        }
    }

    fn integer(&self) -> Option<i64> {
        match *self {
            ConfigNode::Int(number) => Some(*number),
            ConfigNode::Host(host) => host.facts.integer,
            _ => None,
        }
    }

    /// Python's `float(int)`, which rounds the decimal value to the nearest float, as parsing does.
    fn number(&self) -> Option<f64> {
        match *self {
            ConfigNode::Int(number) => Some(*number as f64),
            ConfigNode::Float(number) => Some(*number),
            ConfigNode::Host(host) => host.facts.number,
            _ => None,
        }
    }

    fn text(&self) -> Option<String> {
        self.with_text(str::to_owned)
    }

    fn is_text(&self, text: &str) -> bool {
        self.with_text(|value| value == text).unwrap_or(false)
    }

    fn with_text<R>(&self, read: impl FnOnce(&str) -> R) -> Option<R> {
        match *self {
            ConfigNode::Str(text) => Some(read(text)),
            ConfigNode::Host(host) => host.facts.text.as_deref().map(read),
            _ => None,
        }
    }

    fn python_str(&self) -> String {
        python_str(self)
    }

    fn python_repr(&self) -> String {
        python_repr(self)
    }

    fn is_date_like(&self) -> bool {
        matches!(self, ConfigNode::Host(host) if host.handle.is_date_like())
    }

    fn items(&self) -> Vec<Self> {
        let node: &'a ConfigNode<H> = self;
        match node {
            ConfigNode::List(items) | ConfigNode::Tuple(items) => items.iter().collect(),
            ConfigNode::Host(host) => match &host.children {
                HostChildren::Items(items) => items.iter().collect(),
                _ => Vec::new(),
            },
            _ => Vec::new(),
        }
    }

    fn entries(&self) -> Vec<(Self, Self)> {
        let node: &'a ConfigNode<H> = self;
        match node {
            ConfigNode::Map(entries) => entries.iter().map(|(key, value)| (key, value)).collect(),
            ConfigNode::Host(host) => match &host.children {
                HostChildren::Entries(entries) => {
                    entries.iter().map(|(key, value)| (key, value)).collect()
                }
                _ => Vec::new(),
            },
            _ => Vec::new(),
        }
    }
}

impl<H: HostObject> AuthoredNode for ConfigNode<H> {
    fn kind(&self) -> NodeKind {
        (&self).kind()
    }

    fn integer(&self) -> Option<i64> {
        (&self).integer()
    }

    fn number(&self) -> Option<f64> {
        (&self).number()
    }

    fn text(&self) -> Option<String> {
        (&self).text()
    }

    fn is_text(&self, text: &str) -> bool {
        (&self).is_text(text)
    }

    fn with_text<R>(&self, read: impl FnOnce(&str) -> R) -> Option<R> {
        (&self).with_text(read)
    }

    fn python_str(&self) -> String {
        python_str(self)
    }

    fn python_repr(&self) -> String {
        python_repr(self)
    }

    fn is_date_like(&self) -> bool {
        (&self).is_date_like()
    }

    fn items(&self) -> Vec<Self> {
        (&self).items().into_iter().cloned().collect()
    }

    fn entries(&self) -> Vec<(Self, Self)> {
        (&self)
            .entries()
            .into_iter()
            .map(|(key, value)| (key.clone(), value.clone()))
            .collect()
    }
}
