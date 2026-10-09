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
    /// A `datetime.date` or `datetime.datetime`, by its `str()`.
    Date(&'static str),
    /// An integer beyond `i64`, by its decimal digits.
    BigInt(&'static str),
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
            Self::Float | Self::Date(_) => NodeKind::Other,
            Self::BigInt(digits) => NodeKind::Int {
                negative: digits.starts_with('-'),
            },
        }
    }

    fn integer(&self) -> Option<i64> {
        match self {
            Self::Int(value) => Some(*value),
            _ => None,
        }
    }

    fn number(&self) -> Option<f64> {
        match self {
            Self::Int(value) => value.to_string().parse::<f64>().ok(),
            Self::Float => Some(0.5),
            Self::BigInt(digits) => digits.parse::<f64>().ok(),
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

    fn python_str(&self) -> String {
        match self {
            Self::Null => "None".to_owned(),
            Self::Bool(flag) => if *flag { "True" } else { "False" }.to_owned(),
            Self::Int(value) => value.to_string(),
            Self::Str(text) | Self::Date(text) | Self::BigInt(text) => (*text).to_owned(),
            Self::Float => "0.5".to_owned(),
            Self::List(_) | Self::Map(_) | Self::Tuple(_) => self.python_repr(),
        }
    }

    fn python_repr(&self) -> String {
        match self {
            Self::Str(text) => format!("'{text}'"),
            Self::Date(text) => format!("datetime.date({text})"),
            Self::List(items) => format!("[{}]", reprs(items)),
            Self::Tuple(items) => format!("({})", reprs(items)),
            Self::Map(entries) => format!(
                "{{{}}}",
                entries
                    .iter()
                    .map(|(key, value)| format!("{}: {}", key.python_repr(), value.python_repr()))
                    .collect::<Vec<String>>()
                    .join(", ")
            ),
            _ => self.python_str(),
        }
    }

    fn is_date_like(&self) -> bool {
        matches!(self, Self::Date(_))
    }
}

fn reprs(items: &[Value]) -> String {
    items
        .iter()
        .map(AuthoredNode::python_repr)
        .collect::<Vec<String>>()
        .join(", ")
}
