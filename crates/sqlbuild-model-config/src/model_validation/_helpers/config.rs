//! Effective config values read the way the Python validators read the dict.

use std::collections::HashMap;

use crate::model_validation::_helpers::text::{python_lower, python_strip};
use crate::model_validation::models::Rejected;
use crate::types::{AuthoredNode, NodeKind};

/// Config values by string key; Python's `dict.get` never matches other keys.
pub(crate) struct ConfigView<N> {
    values: HashMap<String, N>,
}

impl<N: AuthoredNode> ConfigView<N> {
    /// View the entries of one config mapping.
    pub(crate) fn new(entries: Vec<(N, N)>) -> Self {
        let mut values: HashMap<String, N> = HashMap::with_capacity(entries.len());
        for (key, value) in entries {
            if let Some(text) = key.text() {
                values.insert(text, value);
            }
        }
        Self { values }
    }

    /// Return whether `key in values`, even when its value is `None`.
    pub(crate) fn contains_key(&self, key: &str) -> bool {
        self.values.contains_key(key)
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

    /// Return whether any of `keys` is set.
    pub(crate) fn any_present(&self, keys: &[&str]) -> bool {
        keys.iter().any(|key| self.present(key))
    }

    /// Read `get_config_str`: a string, `None`, or a rejection for any other type.
    pub(crate) fn string(&self, key: &str) -> Result<Option<String>, Rejected> {
        self.get(key).map(string_value).transpose()
    }

    /// Return whether the value equals `text`, as Python's `==` against a string.
    pub(crate) fn equals(&self, key: &str, text: &str) -> bool {
        self.get(key).is_some_and(|value| value.is_text(text))
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

/// Return `None` for an absent or `None` value, the text of a string, or reject other types.
pub(crate) fn optional_text<N: AuthoredNode>(
    value: Option<&N>,
) -> Result<Option<String>, Rejected> {
    match value {
        Some(node) if node.kind() != NodeKind::Null => string_value(node).map(Some),
        _ => Ok(None),
    }
}

/// Return whether `text in vocabulary`.
pub(crate) fn one_of(text: &str, vocabulary: &[&str]) -> bool {
    vocabulary.contains(&text)
}

/// Return whether an optional string is in `vocabulary`; `None` is not.
pub(crate) fn optional_one_of(text: Option<&str>, vocabulary: &[&str]) -> bool {
    text.is_some_and(|value| one_of(value, vocabulary))
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

/// Return the text of a string whose Python `strip()` is non-empty, or reject.
pub(crate) fn non_blank_string<N: AuthoredNode>(value: &N) -> Result<String, Rejected> {
    let text = string_value(value)?;
    if python_strip(&text)?.is_empty() {
        Err(Rejected)
    } else {
        Ok(text)
    }
}

/// Reject duplicate names under Python's `str.lower()`.
pub(crate) fn reject_case_insensitive_duplicates(names: &[String]) -> Result<(), Rejected> {
    let mut seen = Vec::with_capacity(names.len());
    for name in names {
        let lowered = python_lower(name)?;
        if seen.contains(&lowered) {
            return Err(Rejected);
        }
        seen.push(lowered);
    }
    Ok(())
}
