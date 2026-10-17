//! Native authored header values read as the Python objects discovery projects them to.

use std::cell::Cell;
use std::collections::HashMap;

use sqlbuild_model_config::types::{AuthoredNode, NodeKind};
use sqlbuild_sqltext::compiler::main::header_word_value::header_word_value;
use sqlbuild_sqltext::compiler::models::{AuthoredValue, HeaderWord};

thread_local! {
    /// Whether a read needed Python's `str` or `repr` of a value only Python can spell.
    static INEXACT: Cell<bool> = const { Cell::new(false) };
}

/// One authored header value, or a mapping key, as its Python projection reads.
#[derive(Clone, Copy, Debug)]
pub(crate) enum NativeNode<'a> {
    Value(&'a AuthoredValue),
    Key(&'a str),
}

/// Run `read` and report whether every Python spelling it needed was exact.
pub(crate) fn exactly<T>(read: impl FnOnce() -> T) -> (T, bool) {
    INEXACT.with(|flag| flag.set(false));
    let result: T = read();
    (result, !INEXACT.with(Cell::get))
}

fn inexact() -> String {
    INEXACT.with(|flag| flag.set(true));
    String::new()
}

/// A bare word's projection: Python's `_parse_word_value`.
fn word(text: &str) -> HeaderWord {
    header_word_value(text)
}

/// Whether integer `digits` (with an optional sign) is below zero, as `int(digits) < 0`.
fn negative(digits: &str) -> bool {
    digits.starts_with('-') && digits[1..].bytes().any(|byte| byte != b'0')
}

/// Python's `str(int(digits))`.
fn integer_text(digits: &str) -> String {
    let unsigned: &str = digits.trim_start_matches(['+', '-']);
    let trimmed: &str = unsigned.trim_start_matches('0');
    if trimmed.is_empty() {
        return "0".to_owned();
    }
    if negative(digits) {
        format!("-{trimmed}")
    } else {
        trimmed.to_owned()
    }
}

impl<'a> NativeNode<'a> {
    /// The text of a projected string, or `None`.
    fn as_text(&self) -> Option<&'a str> {
        match self {
            Self::Key(key) => Some(key),
            Self::Value(AuthoredValue::String(text)) => Some(text),
            Self::Value(AuthoredValue::BareWord(text)) => match word(text) {
                HeaderWord::Text => Some(text),
                _ => None,
            },
            Self::Value(_) => None,
        }
    }

    /// The digits of a projected integer, or `None`.
    fn digits(&self) -> Option<String> {
        match self {
            Self::Value(AuthoredValue::BareWord(text)) => match word(text) {
                HeaderWord::Integer(digits) => Some(digits),
                _ => None,
            },
            _ => None,
        }
    }

    /// The owned authored value of a value node; a key projects as its string.
    pub(crate) fn authored(&self) -> AuthoredValue {
        match self {
            Self::Key(key) => AuthoredValue::String((*key).to_owned()),
            Self::Value(value) => (*value).clone(),
        }
    }
}

impl AuthoredNode for NativeNode<'_> {
    fn kind(&self) -> NodeKind {
        let Self::Value(value) = self else {
            return NodeKind::Str;
        };
        match value {
            AuthoredValue::Null => NodeKind::Null,
            AuthoredValue::Boolean(flag) => NodeKind::Bool(*flag),
            AuthoredValue::String(_) => NodeKind::Str,
            AuthoredValue::List(_) => NodeKind::List,
            AuthoredValue::Tuple(_) => NodeKind::Tuple,
            AuthoredValue::Map(_) => NodeKind::Map,
            AuthoredValue::BareWord(text) => match word(text) {
                HeaderWord::Bool(flag) => NodeKind::Bool(flag),
                HeaderWord::Null => NodeKind::Null,
                HeaderWord::Integer(digits) => NodeKind::Int {
                    negative: negative(&digits),
                },
                HeaderWord::Float(_) => NodeKind::Other,
                HeaderWord::Text => NodeKind::Str,
            },
            AuthoredValue::Set(_)
            | AuthoredValue::TypedConstant(_)
            | AuthoredValue::InlineSqlHook(_)
            | AuthoredValue::NamedSqlHook(..)
            | AuthoredValue::PythonHook(..) => NodeKind::Other,
        }
    }

    fn integer(&self) -> Option<i64> {
        let digits: String = self.digits()?;
        let Ok(number) = digits.parse::<i64>() else {
            return None;
        };
        Some(number)
    }

    fn number(&self) -> Option<f64> {
        if let Some(digits) = self.digits() {
            let Ok(number) = digits.parse::<f64>() else {
                return None;
            };
            return Some(number);
        }
        match self {
            Self::Value(AuthoredValue::BareWord(text)) => match word(text) {
                HeaderWord::Float(number) => Some(number),
                _ => None,
            },
            _ => None,
        }
    }

    fn text(&self) -> Option<String> {
        self.as_text().map(str::to_owned)
    }

    fn with_text<R>(&self, read: impl FnOnce(&str) -> R) -> Option<R> {
        self.as_text().map(read)
    }

    fn is_text(&self, text: &str) -> bool {
        self.as_text() == Some(text)
    }

    fn python_str(&self) -> String {
        if let Some(text) = self.as_text() {
            return text.to_owned();
        }
        if let Some(digits) = self.digits() {
            return integer_text(&digits);
        }
        match self.kind() {
            NodeKind::Null => "None".to_owned(),
            NodeKind::Bool(true) => "True".to_owned(),
            NodeKind::Bool(false) => "False".to_owned(),
            _ => inexact(),
        }
    }

    fn python_repr(&self) -> String {
        match self.kind() {
            NodeKind::Null | NodeKind::Bool(_) | NodeKind::Int { .. } => self.python_str(),
            _ => inexact(),
        }
    }

    fn is_date_like(&self) -> bool {
        false
    }

    fn items(&self) -> Vec<Self> {
        match self {
            Self::Value(AuthoredValue::List(items) | AuthoredValue::Tuple(items)) => {
                items.iter().map(Self::Value).collect()
            }
            _ => Vec::new(),
        }
    }

    fn entries(&self) -> Vec<(Self, Self)> {
        match self {
            Self::Value(AuthoredValue::Map(entries)) => dict_entries(entries)
                .into_iter()
                .map(|(key, value)| (Self::Key(key), Self::Value(value)))
                .collect(),
            _ => Vec::new(),
        }
    }
}

/// Entries as the Python dict built from them holds them: first position, last value.
pub(crate) fn dict_entries(entries: &[(String, AuthoredValue)]) -> Vec<(&str, &AuthoredValue)> {
    let mut kept: Vec<(&str, &AuthoredValue)> = Vec::with_capacity(entries.len());
    let mut positions: HashMap<&str, usize> = HashMap::with_capacity(entries.len());
    for (key, value) in entries {
        match positions.get(key.as_str()) {
            Some(&index) => kept[index].1 = value,
            None => {
                positions.insert(key, kept.len());
                kept.push((key, value));
            }
        }
    }
    kept
}
