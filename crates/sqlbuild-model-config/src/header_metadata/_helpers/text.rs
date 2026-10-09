//! Text checks that agree with Python's `str` methods, and the errors they raise.

use sqlbuild_core::text::main::python_strip::python_strip;

use crate::errors::ConfigError;
use crate::types::{AuthoredNode, NodeKind};

/// Where one parse reports its errors: the file path and the label the messages name.
#[derive(Clone, Copy)]
pub(crate) struct Site<'a> {
    pub(crate) path: &'a str,
    pub(crate) label: &'a str,
}

impl Site<'_> {
    /// The `CompileInputError` `<path> <label> <text>`.
    pub(crate) fn error(&self, text: &str) -> ConfigError {
        ConfigError::compile(format!("{} {} {text}", self.path, self.label))
    }
}

/// Return the text of a string whose `strip()` Python finds non-empty, `None` otherwise.
pub(crate) fn non_blank_text<N: AuthoredNode>(node: &N) -> Option<String> {
    node.text().filter(|text| !python_strip(text).is_empty())
}

/// Read `optional_named_string`: `None`, or a string `strip()` finds non-empty.
pub(crate) fn optional_text<N: AuthoredNode>(
    node: Option<&N>,
    site: Site<'_>,
    key: &str,
) -> Result<Option<N>, ConfigError> {
    match node {
        None => Ok(None),
        Some(value) if value.kind() == NodeKind::Null => Ok(None),
        Some(value) => match non_blank_text(value) {
            Some(_) => Ok(Some(value.clone())),
            None => Err(site.error(&format!("'{key}' must be a non-empty string"))),
        },
    }
}

/// Read `optional_named_bool`: `None`, or a boolean.
pub(crate) fn optional_bool<N: AuthoredNode>(
    node: Option<&N>,
    site: Site<'_>,
    key: &str,
) -> Result<Option<N>, ConfigError> {
    match node.map(AuthoredNode::kind) {
        None | Some(NodeKind::Null) => Ok(None),
        Some(NodeKind::Bool(_)) => Ok(node.cloned()),
        Some(_) => Err(site.error(&format!("'{key}' must be a boolean"))),
    }
}

/// Read a non-negative non-boolean integer option, or `None`.
pub(crate) fn optional_count<N: AuthoredNode>(
    node: Option<&N>,
    site: Site<'_>,
    key: &str,
) -> Result<Option<N>, ConfigError> {
    match node.map(AuthoredNode::kind) {
        None | Some(NodeKind::Null) => Ok(None),
        Some(NodeKind::Int { negative: false }) => Ok(node.cloned()),
        Some(_) => Err(site.error(&format!("'{key}' must be a non-negative integer"))),
    }
}

/// Return the mapping entry whose key is the string `key`.
pub(crate) fn entry<'entries, N: AuthoredNode>(
    entries: &'entries [(N, N)],
    key: &str,
) -> Option<&'entries N> {
    entries
        .iter()
        .find(|(name, _)| name.is_text(key))
        .map(|(_, value)| value)
}
