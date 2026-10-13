//! Lookups over a profile output with Python `dict` semantics.

use crate::dbt_profile::models::{ProfileEntry, ProfileValue};

/// A profile output, read as Python reads the rendered `dict`.
pub(crate) struct Output<'a>(pub(crate) &'a [ProfileEntry]);

impl Output<'_> {
    /// The index of `key`, when present.
    pub(crate) fn index(&self, key: &str) -> Option<usize> {
        self.0
            .iter()
            .position(|entry| entry.key.as_deref() == Some(key))
    }

    /// `output.get(keys[0], output.get(keys[1], ...))`: the first present key's index.
    pub(crate) fn first_present(&self, keys: &[&str]) -> Option<usize> {
        keys.iter().find_map(|key| self.index(key))
    }

    /// The first present key's index, unless its value is `None`.
    pub(crate) fn first_value(&self, keys: &[&str]) -> Option<usize> {
        self.first_present(keys)
            .filter(|index| self.0[*index].value != ProfileValue::Null)
    }

    /// `_string_or_none(output.get(...))`: a non-empty string value.
    pub(crate) fn non_empty_text(&self, keys: &[&str]) -> Option<String> {
        self.text_at(self.first_present(keys))
            .filter(|text| !text.is_empty())
    }

    /// The string value at `index`, when it is a string.
    pub(crate) fn text_at(&self, index: Option<usize>) -> Option<String> {
        match &self.0[index?].value {
            ProfileValue::Text(text) => Some(text.clone()),
            _ => None,
        }
    }

    /// Whether the value of `key` is exactly `True`.
    pub(crate) fn is_true(&self, key: &str) -> bool {
        self.index(key)
            .is_some_and(|index| self.0[index].value == ProfileValue::Bool(true))
    }

    /// Named keys present in the output that are listed in `keys`, sorted.
    pub(crate) fn sorted_present(&self, keys: &[&str], with_value: bool) -> Vec<String> {
        let mut present: Vec<String> = self
            .0
            .iter()
            .filter(|entry| !with_value || entry.value != ProfileValue::Null)
            .filter_map(|entry| entry.key.clone())
            .filter(|key| keys.contains(&key.as_str()))
            .collect();
        present.sort_unstable();
        present
    }
}
