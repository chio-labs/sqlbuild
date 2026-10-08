//! Text checks that agree with Python's `str` methods or defer, and the errors they raise.

use crate::errors::ConfigError;
use crate::header_metadata::models::HeaderMetadataStop;
use crate::types::{AuthoredNode, NodeKind};

/// Where one parse reports its errors: the file path and the label the messages name.
#[derive(Clone, Copy)]
pub(crate) struct Site<'a> {
    pub(crate) path: &'a str,
    pub(crate) label: &'a str,
}

impl Site<'_> {
    /// The `CompileInputError` `<path> <label> <text>`.
    pub(crate) fn error(&self, text: &str) -> HeaderMetadataStop {
        HeaderMetadataStop::Error(ConfigError::compile(format!(
            "{} {} {text}",
            self.path, self.label
        )))
    }
}

/// Return the text of a string whose `strip()` Python finds non-empty, `None` otherwise.
pub(crate) fn non_blank_text<N: AuthoredNode>(
    node: &N,
) -> Result<Option<String>, HeaderMetadataStop> {
    if node.kind() != NodeKind::Str {
        return Ok(None);
    }
    let text = node.text().ok_or(HeaderMetadataStop::Unsupported)?;
    if text
        .bytes()
        .any(|byte| byte.is_ascii() && !is_python_space(byte))
    {
        Ok(Some(text))
    } else if text.is_ascii() {
        Ok(None)
    } else {
        Err(HeaderMetadataStop::Unsupported)
    }
}

/// Read `optional_named_string`: `None`, or a string `strip()` finds non-empty.
pub(crate) fn optional_text<N: AuthoredNode>(
    node: Option<&N>,
    site: Site<'_>,
    key: &str,
) -> Result<Option<N>, HeaderMetadataStop> {
    match node {
        None => Ok(None),
        Some(value) if value.kind() == NodeKind::Null => Ok(None),
        Some(value) => match non_blank_text(value)? {
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
) -> Result<Option<N>, HeaderMetadataStop> {
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
) -> Result<Option<N>, HeaderMetadataStop> {
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

/// Return Python's `text.strip()` for ASCII text.
pub(crate) fn ascii_strip(text: &str) -> &str {
    text.trim_matches(|character: char| character.is_ascii() && is_python_space(character as u8))
}

/// ASCII characters Python's `str.isspace` accepts, including the information separators.
fn is_python_space(byte: u8) -> bool {
    matches!(byte, b'\t'..=b'\r' | 0x1c..=0x1f | b' ')
}
