//! Effective config values read the way the Python validators read the dict.

use std::collections::HashMap;
use std::fmt::Display;

use crate::errors::ConfigError;
use crate::model_validation::_helpers::text::{python_lower, python_strip};
use crate::model_validation::models::{Rejected, ValidationStop};
use crate::types::{AuthoredNode, NodeKind};

/// Config values by string key; Python's `dict.get` never matches other keys.
pub(crate) struct ConfigView<'a, N> {
    values: HashMap<String, N>,
    /// The model name every validator message starts with.
    pub(crate) model_name: &'a str,
}

impl<'a, N: AuthoredNode> ConfigView<'a, N> {
    /// View the entries of one config mapping for the model `model_name`.
    pub(crate) fn new(entries: Vec<(N, N)>, model_name: &'a str) -> Self {
        let mut values: HashMap<String, N> = HashMap::with_capacity(entries.len());
        for (key, value) in entries {
            if let Some(text) = key.text() {
                values.insert(text, value);
            }
        }
        Self { values, model_name }
    }

    /// Return `values[key]` when the key is present, even when its value is `None`.
    pub(crate) fn raw(&self, key: &str) -> Option<&N> {
        self.values.get(key)
    }

    /// Return `values.get(key)` unless it is absent or `None`.
    pub(crate) fn get(&self, key: &str) -> Option<&N> {
        self.values
            .get(key)
            .filter(|value| value.kind() != NodeKind::Null)
    }

    /// Return whether `values.get(key) is not None`.
    pub(crate) fn present(&self, key: &str) -> bool {
        self.get(key).is_some()
    }

    /// Return the first of `keys` that is set, in order.
    pub(crate) fn first_present<'k>(&self, keys: &[&'k str]) -> Option<&'k str> {
        keys.iter().copied().find(|key| self.present(key))
    }

    /// Read `get_config_str`: a string, `None`, or the type error it raises for other values.
    pub(crate) fn string(&self, key: &str) -> Result<Option<String>, ValidationStop> {
        match self.get(key) {
            None => Ok(None),
            Some(value) if value.kind() == NodeKind::Str => Ok(Some(value.text().ok_or(Rejected)?)),
            Some(_) => Err(ValidationStop::Error(ConfigError::config_value_type(key))),
        }
    }

    /// Return whether the value equals `text`, as Python's `==` against a string.
    pub(crate) fn equals(&self, key: &str, text: &str) -> bool {
        self.get(key).is_some_and(|value| value.is_text(text))
    }

    /// The validator error `model '<name>': <text>`.
    pub(crate) fn error(&self, text: impl Display) -> ValidationStop {
        ValidationStop::Error(self.config_error(text))
    }

    /// The `CompileInputError` `model '<name>': <text>`.
    pub(crate) fn config_error(&self, text: impl Display) -> ConfigError {
        ConfigError::compile(format!("model '{}': {text}", self.model_name))
    }
}

/// Return the text of a string value, or reject any other type.
pub(crate) fn string_value<N: AuthoredNode>(value: &N) -> Result<String, Rejected> {
    if value.kind() == NodeKind::Str {
        value.text().ok_or(Rejected)
    } else {
        Err(Rejected)
    }
}

/// Return the text of a string value, `None` for another type, or reject unreadable text.
pub(crate) fn text_if_string<N: AuthoredNode>(value: &N) -> Result<Option<String>, Rejected> {
    if value.kind() == NodeKind::Str {
        value.text().map(Some).ok_or(Rejected)
    } else {
        Ok(None)
    }
}

/// Return Python's `str(value)` for strings, integers, booleans and `None`, or reject.
pub(crate) fn python_str<N: AuthoredNode>(value: &N) -> Result<String, Rejected> {
    match value.kind() {
        NodeKind::Str => value.text().ok_or(Rejected),
        NodeKind::Int { .. } => value
            .integer()
            .map(|number| number.to_string())
            .ok_or(Rejected),
        NodeKind::Bool(flag) => Ok(if flag { "True" } else { "False" }.to_owned()),
        NodeKind::Null => Ok("None".to_owned()),
        _ => Err(Rejected),
    }
}

/// Return Python's `repr(value)` for printable ASCII strings and scalars, or reject.
pub(crate) fn python_repr<N: AuthoredNode>(value: &N) -> Result<String, Rejected> {
    if value.kind() != NodeKind::Str {
        return python_str(value);
    }
    let text = value.text().ok_or(Rejected)?;
    python_text_repr(&text)
}

/// Return Python's `repr(text)` for printable ASCII text, or reject.
pub(crate) fn python_text_repr(text: &str) -> Result<String, Rejected> {
    if !text.bytes().all(|byte| (b' '..=b'~').contains(&byte)) {
        return Err(Rejected);
    }
    let quote = if text.contains('\'') && !text.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut repr = String::with_capacity(text.len() + 2);
    repr.push(quote);
    for character in text.chars() {
        if character == '\\' || character == quote {
            repr.push('\\');
        }
        repr.push(character);
    }
    repr.push(quote);
    Ok(repr)
}

/// Return whether `text in vocabulary`.
pub(crate) fn one_of(text: &str, vocabulary: &[&str]) -> bool {
    vocabulary.contains(&text)
}

/// Return the vocabulary sorted and joined with `, `, as the Python messages list it.
pub(crate) fn sorted_values(vocabulary: &[&str]) -> String {
    let mut values: Vec<&str> = vocabulary.to_vec();
    values.sort_unstable();
    values.join(", ")
}

/// Read `_string_sequence`: a string, or the strings of a list or tuple; reject unreadable text.
pub(crate) fn string_sequence<N: AuthoredNode>(value: Option<&N>) -> Result<Vec<String>, Rejected> {
    match value.map(|node| (node.kind(), node)) {
        Some((NodeKind::Str, node)) => string_value(node).map(|text| vec![text]),
        Some((NodeKind::List | NodeKind::Tuple, node)) => node
            .items()
            .iter()
            .filter(|item| item.kind() == NodeKind::Str)
            .map(string_value)
            .collect(),
        _ => Ok(Vec::new()),
    }
}

/// Return whether a value is set and not an empty list or tuple, like `_has_config_value`.
pub(crate) fn has_config_value<N: AuthoredNode>(value: Option<&N>) -> bool {
    value.is_some_and(|node| {
        !matches!(node.kind(), NodeKind::List | NodeKind::Tuple) || !node.items().is_empty()
    })
}

/// Check that a value is a string whose Python `strip()` is non-empty, or reject.
pub(crate) fn non_blank_string_check<N: AuthoredNode>(value: &N) -> Result<bool, Rejected> {
    match text_if_string(value)? {
        Some(text) => Ok(!python_strip(&text)?.is_empty()),
        None => Ok(false),
    }
}

/// Return whether two names are equal under Python's `str.lower()`, or reject.
pub(crate) fn same_lowered(left: &str, right: &str) -> Result<bool, Rejected> {
    Ok(python_lower(left)? == python_lower(right)?)
}
