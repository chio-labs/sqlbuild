//! Effective config values read the way the Python validators read the dict.

use std::collections::HashMap;
use std::fmt::Display;

use sqlbuild_core::text::main::python_strip::python_strip;
use sqlbuild_core::text::models::PythonText;

use crate::errors::ConfigError;
use crate::model_validation::_helpers::durations::{Duration, parse_duration};
use crate::model_validation::constants::SETTING_SNIPPET_INDENT;
use crate::model_validation::errors::DurationNumberError;
use crate::model_validation::models::ValidationStop;
use crate::types::{AuthoredNode, NodeKind};

/// Config values by string key; Python's `dict.get` never matches other keys.
pub(crate) struct ConfigView<'a, N> {
    values: HashMap<String, N>,
    /// The model name every validator message starts with.
    pub(crate) model_name: &'a str,
    /// The Python string semantics the validators follow.
    pub(crate) python: PythonText,
}

impl<'a, N: AuthoredNode> ConfigView<'a, N> {
    /// View the entries of one config mapping for the model `model_name`.
    pub(crate) fn new(entries: Vec<(N, N)>, model_name: &'a str, python: PythonText) -> Self {
        let mut values: HashMap<String, N> = HashMap::with_capacity(entries.len());
        for (key, value) in entries {
            if let Some(text) = key.text() {
                values.insert(text, value);
            }
        }
        Self {
            values,
            model_name,
            python,
        }
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
            Some(value) if value.kind() == NodeKind::Str => Ok(value.text()),
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

    /// Parse `key`'s duration `text`, raising for a duration SQLBuild cannot read exactly.
    pub(crate) fn duration(
        &self,
        key: &str,
        text: &str,
    ) -> Result<Option<Duration>, ValidationStop> {
        self.duration_written_as(key, text, "7d")
    }

    /// Parse `key`'s duration `text`; a raised error's help shows `key '<example>'`.
    pub(crate) fn duration_written_as(
        &self,
        key: &str,
        text: &str,
        example: &str,
    ) -> Result<Option<Duration>, ValidationStop> {
        parse_duration(self.python, text).map_err(|error| {
            let (problem, purpose) = match error {
                DurationNumberError::NonAsciiDigits => (
                    "uses digits outside ASCII",
                    format!("write {key} with ASCII digits 0-9"),
                ),
                DurationNumberError::TooLarge => (
                    "has a number larger than a 64-bit integer",
                    format!("use a {key} whose numbers fit in 64 bits"),
                ),
            };
            ValidationStop::Error(
                self.config_error(format!("{key} '{text}' {problem}"))
                    .with_help(model_header_help(&purpose, &format!("{key} '{example}'"))),
            )
        })
    }

    /// The error for an integer `key` beyond 64 bits; `entry` writes the header entry for a bound.
    pub(crate) fn integer_out_of_range(
        &self,
        key: &str,
        value: &N,
        entry: impl Fn(i64) -> String,
    ) -> ValidationStop {
        let (comparison, bound) = match value.kind() {
            NodeKind::Int { negative: true } => ("smaller", i64::MIN),
            _ => ("larger", i64::MAX),
        };
        ValidationStop::Error(
            self.config_error(format!(
                "{key} {} is {comparison} than a 64-bit integer",
                value.python_str()
            ))
            .with_help(model_header_help(
                &format!("set {key} to a value that fits in 64 bits"),
                &entry(bound),
            )),
        )
    }
}

/// Return the text of a string value, or `None` for another type.
pub(crate) fn text_if_string<N: AuthoredNode>(value: &N) -> Option<String> {
    if value.kind() == NodeKind::Str {
        value.text()
    } else {
        None
    }
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

/// Read `_string_sequence`: a string, or the strings of a list or tuple.
pub(crate) fn string_sequence<N: AuthoredNode>(value: Option<&N>) -> Vec<String> {
    match value.map(|node| (node.kind(), node)) {
        Some((NodeKind::Str, node)) => node.text().into_iter().collect(),
        Some((NodeKind::List | NodeKind::Tuple, node)) => {
            node.items().iter().filter_map(text_if_string).collect()
        }
        _ => Vec::new(),
    }
}

/// Return whether a value is set and not an empty list or tuple, like `_has_config_value`.
pub(crate) fn has_config_value<N: AuthoredNode>(value: Option<&N>) -> bool {
    value.is_some_and(|node| {
        !matches!(node.kind(), NodeKind::List | NodeKind::Tuple) || !node.items().is_empty()
    })
}

/// Check that a value is a string whose Python `strip()` is non-empty.
pub(crate) fn non_blank_string_check<N: AuthoredNode>(value: &N) -> bool {
    text_if_string(value).is_some_and(|text| !python_strip(&text).is_empty())
}

/// Return whether two names are equal under Python's `str.lower()`.
pub(crate) fn same_lowered(left: &str, right: &str) -> bool {
    python_lower(left) == python_lower(right)
}

/// Return Python's `text.lower()`.
pub(crate) fn python_lower(text: &str) -> String {
    text.to_lowercase()
}

/// Return `model_header_help`: the purpose, then the exact MODEL header entry to add.
pub(crate) fn model_header_help(purpose: &str, entry: &str) -> String {
    let indent = SETTING_SNIPPET_INDENT;
    format!(
        "{purpose}, add this to the MODEL header:\n{indent}MODEL (\n{indent}  {entry},\n\
         {indent}  ...\n{indent});"
    )
}
