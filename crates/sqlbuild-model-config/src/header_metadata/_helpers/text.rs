//! Text checks that agree with Python's `str` methods or defer.

use crate::header_metadata::models::HeaderMetadataDeferral;
use crate::types::{AuthoredNode, NodeKind};

/// Return the text of a string whose `strip()` Python finds non-empty.
pub(crate) fn non_blank_text<N: AuthoredNode>(node: &N) -> Result<String, HeaderMetadataDeferral> {
    if node.kind() != NodeKind::Str {
        return Err(HeaderMetadataDeferral::Invalid);
    }
    let text = node.text().ok_or(HeaderMetadataDeferral::Unsupported)?;
    if text
        .bytes()
        .any(|byte| byte.is_ascii() && !is_python_space(byte))
    {
        Ok(text)
    } else if text.is_ascii() {
        Err(HeaderMetadataDeferral::Invalid)
    } else {
        Err(HeaderMetadataDeferral::Unsupported)
    }
}

/// Return `None` for Python's `None`, or the node of a string `strip()` finds non-empty.
pub(crate) fn optional_text<N: AuthoredNode>(
    node: Option<&N>,
) -> Result<Option<N>, HeaderMetadataDeferral> {
    match node {
        None => Ok(None),
        Some(value) if value.kind() == NodeKind::Null => Ok(None),
        Some(value) => non_blank_text(value).map(|_| Some(value.clone())),
    }
}

/// Return `None` for Python's `None`, or the node of a boolean.
pub(crate) fn optional_bool<N: AuthoredNode>(
    node: Option<&N>,
) -> Result<Option<N>, HeaderMetadataDeferral> {
    match node.map(AuthoredNode::kind) {
        None | Some(NodeKind::Null) => Ok(None),
        Some(NodeKind::Bool(_)) => Ok(node.cloned()),
        Some(_) => Err(HeaderMetadataDeferral::Invalid),
    }
}

/// Return `None` for Python's `None`, or the node of a non-negative non-boolean integer.
pub(crate) fn optional_count<N: AuthoredNode>(
    node: Option<&N>,
) -> Result<Option<N>, HeaderMetadataDeferral> {
    match node.map(AuthoredNode::kind) {
        None | Some(NodeKind::Null) => Ok(None),
        Some(NodeKind::Int { negative: false }) => Ok(node.cloned()),
        Some(_) => Err(HeaderMetadataDeferral::Invalid),
    }
}

/// Return whether `name` fully matches Python's `^[a-z](?:[a-z0-9_]*[a-z0-9])?$` identity pattern.
pub(crate) fn is_snake_case(name: &str) -> bool {
    let bytes = name.as_bytes();
    match (bytes.first(), bytes.last()) {
        (Some(first), Some(last)) => {
            first.is_ascii_lowercase()
                && (last.is_ascii_lowercase() || last.is_ascii_digit())
                && bytes
                    .iter()
                    .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || *byte == b'_')
        }
        _ => false,
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

/// ASCII characters Python's `str.isspace` accepts, including the information separators.
fn is_python_space(byte: u8) -> bool {
    matches!(byte, b'\t'..=b'\r' | 0x1c..=0x1f | b' ')
}
