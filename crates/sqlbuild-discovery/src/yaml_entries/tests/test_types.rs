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

/// One loaded schema document and its seeds or the first parse error.
pub(super) struct SchemaDocumentTestCase {
    pub(super) description: &'static str,
    pub(super) document: Node,
    pub(super) in_seeds_directory: bool,
    pub(super) expected_seeds: Result<Vec<String>, String>,
}

/// One loaded sources document and its sources or the first parse error.
pub(super) struct SourcesDocumentTestCase {
    pub(super) description: &'static str,
    pub(super) document: Node,
    pub(super) expected_sources: Result<Vec<String>, String>,
}

/// One freshness duration and its whole minutes, `None` when Python rejects it.
pub(super) struct FreshnessDurationTestCase {
    pub(super) description: &'static str,
    pub(super) text: &'static str,
    pub(super) expected_minutes: Option<u128>,
}

/// The summary lines a parse returns.
pub(super) fn lines(lines: &[&str]) -> Result<Vec<String>, String> {
    Ok(lines.iter().map(|line| (*line).to_owned()).collect())
}

/// The parse error message.
pub(super) fn parse_error(message: &str) -> Result<Vec<String>, String> {
    Err(message.to_owned())
}
