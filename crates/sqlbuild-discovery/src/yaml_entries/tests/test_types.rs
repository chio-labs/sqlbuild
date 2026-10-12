use sqlbuild_model_config::types::{AuthoredNode, NodeKind};

/// An authored value tree standing in for the Python objects a loaded YAML document holds.
#[derive(Clone, Debug, PartialEq)]
pub(crate) enum Node {
    Null,
    Bool(bool),
    Int(i64),
    Str(String),
    List(Vec<Node>),
    Map(Vec<(Node, Node)>),
}

pub(crate) fn text(value: &str) -> Node {
    Node::Str(value.to_owned())
}

pub(crate) fn map(entries: Vec<(&str, Node)>) -> Node {
    Node::Map(
        entries
            .into_iter()
            .map(|(key, value)| (text(key), value))
            .collect(),
    )
}

impl AuthoredNode for Node {
    fn kind(&self) -> NodeKind {
        match self {
            Self::Null => NodeKind::Null,
            Self::Bool(value) => NodeKind::Bool(*value),
            Self::Int(value) => NodeKind::Int {
                negative: *value < 0,
            },
            Self::Str(_) => NodeKind::Str,
            Self::List(_) => NodeKind::List,
            Self::Map(_) => NodeKind::Map,
        }
    }

    fn integer(&self) -> Option<i64> {
        match self {
            Self::Int(value) => Some(*value),
            _ => None,
        }
    }

    fn number(&self) -> Option<f64> {
        self.integer().map(|value| value as f64)
    }

    fn text(&self) -> Option<String> {
        match self {
            Self::Str(value) => Some(value.clone()),
            _ => None,
        }
    }

    fn is_text(&self, text: &str) -> bool {
        matches!(self, Self::Str(value) if value == text)
    }

    fn with_text<R>(&self, read: impl FnOnce(&str) -> R) -> Option<R> {
        match self {
            Self::Str(value) => Some(read(value)),
            _ => None,
        }
    }

    fn python_str(&self) -> String {
        match self {
            Self::Null => "None".to_owned(),
            Self::Bool(true) => "True".to_owned(),
            Self::Bool(false) => "False".to_owned(),
            Self::Int(value) => value.to_string(),
            Self::Str(value) => value.clone(),
            other => format!("{other:?}"),
        }
    }

    fn python_repr(&self) -> String {
        self.python_str()
    }

    fn is_date_like(&self) -> bool {
        false
    }

    fn items(&self) -> Vec<Self> {
        match self {
            Self::List(items) => items.clone(),
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
