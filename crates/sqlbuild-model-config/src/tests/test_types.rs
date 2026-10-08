use crate::types::{AuthoredNode, NodeKind};

/// An authored value tree standing in for the Python objects the bindings read.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum Value {
    Null,
    Bool(bool),
    Int(i64),
    Str(&'static str),
    List(Vec<Value>),
    Map(Vec<(Value, Value)>),
    Tuple(Vec<Value>),
    Float,
}

impl AuthoredNode for Value {
    fn kind(&self) -> NodeKind {
        match self {
            Self::Null => NodeKind::Null,
            Self::Bool(flag) => NodeKind::Bool(*flag),
            Self::Int(value) => NodeKind::Int {
                negative: *value < 0,
            },
            Self::Str(_) => NodeKind::Str,
            Self::List(_) => NodeKind::List,
            Self::Map(_) => NodeKind::Map,
            Self::Tuple(_) => NodeKind::Tuple,
            Self::Float => NodeKind::Other,
        }
    }

    fn integer(&self) -> Option<i64> {
        match self {
            Self::Int(value) => Some(*value),
            _ => None,
        }
    }

    fn text(&self) -> Option<String> {
        match self {
            Self::Str(text) => Some((*text).to_owned()),
            _ => None,
        }
    }

    fn with_text<R>(&self, read: impl FnOnce(&str) -> R) -> Option<R> {
        match self {
            Self::Str(text) => Some(read(text)),
            _ => None,
        }
    }

    fn is_text(&self, text: &str) -> bool {
        matches!(self, Self::Str(value) if *value == text)
    }

    fn items(&self) -> Vec<Self> {
        match self {
            Self::List(items) | Self::Tuple(items) => items.clone(),
            _ => Vec::new(),
        }
    }

    fn entries(&self) -> Vec<(Self, Self)> {
        match self {
            Self::Map(entries) => entries.clone(),
            _ => Vec::new(),
        }
    }
}
