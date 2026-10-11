//! A compiled dynamic column family `name_pattern`.

use regex::Regex;

/// A `name_pattern` compiled to match whole column names.
#[derive(Clone, Debug)]
pub struct NamePattern {
    pub(crate) regex: Regex,
}

impl NamePattern {
    /// Whether `column_name` wholly matches the pattern.
    pub fn matches(&self, column_name: &str) -> bool {
        self.regex.is_match(column_name)
    }
}
