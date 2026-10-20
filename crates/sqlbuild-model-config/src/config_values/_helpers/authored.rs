//! Config values read as authored values, as `PyNode` reads the Python objects they mirror.

use crate::config_values::_helpers::reprs::{python_repr, python_str};
use crate::config_values::models::{ConfigNode, HostChildren};
use crate::types::{AuthoredNode, NodeKind};

impl<H: Clone> AuthoredNode for ConfigNode<H> {
    fn kind(&self) -> NodeKind {
        match self {
            Self::Null => NodeKind::Null,
            Self::Bool(flag) => NodeKind::Bool(*flag),
            Self::Int(number) => NodeKind::Int {
                negative: *number < 0,
            },
            Self::Float(_) => NodeKind::Other,
            Self::Str(_) => NodeKind::Str,
            Self::List(_) => NodeKind::List,
            Self::Tuple(_) => NodeKind::Tuple,
            Self::Map(_) => NodeKind::Map,
            Self::Host(host) => host.facts.kind,
        }
    }

    fn integer(&self) -> Option<i64> {
        match self {
            Self::Int(number) => Some(*number),
            Self::Host(host) => host.facts.integer,
            _ => None,
        }
    }

    /// Python's `float(int)`, which rounds the decimal value to the nearest float, as parsing does.
    fn number(&self) -> Option<f64> {
        match self {
            Self::Int(number) => Some(*number as f64),
            Self::Float(number) => Some(*number),
            Self::Host(host) => host.facts.number,
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
        match self {
            Self::Str(text) => Some(read(text)),
            Self::Host(host) => host.facts.text.as_deref().map(read),
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
        matches!(self, Self::Host(host) if host.facts.date_like)
    }

    fn items(&self) -> Vec<Self> {
        match self {
            Self::List(items) | Self::Tuple(items) => items.clone(),
            Self::Host(host) => match &host.children {
                HostChildren::Items(items) => items.clone(),
                _ => Vec::new(),
            },
            _ => Vec::new(),
        }
    }

    fn entries(&self) -> Vec<(Self, Self)> {
        match self {
            Self::Map(entries) => entries.clone(),
            Self::Host(host) => match &host.children {
                HostChildren::Entries(entries) => entries.clone(),
                _ => Vec::new(),
            },
            _ => Vec::new(),
        }
    }
}
