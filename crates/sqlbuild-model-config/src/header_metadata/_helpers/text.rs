//! Text checks that agree with Python's `str` methods, and the errors they raise.

use crate::model_validation::constants::SETTING_SNIPPET_INDENT;

use sqlbuild_core::text::main::python_strip::python_strip;

use crate::errors::ConfigError;
use crate::types::{AuthoredNode, NodeKind};

/// Where one parse reports its errors: the file path and the label the messages name.
#[derive(Clone, Copy)]
pub(crate) struct Site<'a> {
    pub(crate) path: &'a str,
    pub(crate) label: &'a str,
    /// The column whose metadata is read, or `None` at the model level.
    pub(crate) column: Option<&'a str>,
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

/// Read a non-negative integer option of audit `definition` that fits in 64 bits; help repeats `options`.
pub(crate) fn optional_count<N: AuthoredNode>(
    node: Option<&N>,
    site: Site<'_>,
    option: (&str, &str, &[(N, N)]),
) -> Result<Option<N>, ConfigError> {
    let (definition, key, options) = option;
    match (
        node.map(AuthoredNode::kind),
        node.and_then(AuthoredNode::integer),
    ) {
        (None | Some(NodeKind::Null), _) => Ok(None),
        (Some(NodeKind::Int { negative: false }), Some(_)) => Ok(node.cloned()),
        (Some(NodeKind::Int { negative: false }), None) => Err(site
            .error(&format!(
                "'{key}' {} is larger than a 64-bit integer",
                node.map(AuthoredNode::python_str).unwrap_or_default()
            ))
            .with_help(count_help(site, (definition, options), key))),
        (Some(_), _) => Err(site.error(&format!("'{key}' must be a non-negative integer"))),
    }
}

/// The MODEL header help repeating the audit call with option `key` set to the largest 64-bit integer.
fn count_help<N: AuthoredNode>(
    site: Site<'_>,
    (definition, options): (&str, &[(N, N)]),
    key: &str,
) -> String {
    let rendered: Vec<String> = options
        .iter()
        .map(|(name, value)| {
            let name: String = name.text().unwrap_or_else(|| name.python_str());
            if name == key {
                format!("{name} {}", i64::MAX)
            } else {
                format!("{name} {}", header_value(value))
            }
        })
        .collect();
    let audits: String = format!("audits [{definition} ({})]", rendered.join(", "));
    let entry: String = site.column.map_or_else(
        || audits.clone(),
        |column| format!("columns ({column} ({audits}))"),
    );
    let indent = SETTING_SNIPPET_INDENT;
    format!(
        "set {key} to a value that fits in 64 bits, add this to the MODEL header:\n{indent}MODEL (\n\
         {indent}  {entry},\n{indent}  ...\n{indent});"
    )
}

/// One authored value as MODEL header syntax: quoted strings, `[...]` lists and `(key value)` maps.
fn header_value<N: AuthoredNode>(node: &N) -> String {
    match node.kind() {
        NodeKind::Null => "null".to_owned(),
        NodeKind::Bool(value) => value.to_string(),
        NodeKind::Str => {
            let text: String = node.text().unwrap_or_default();
            format!("\"{}\"", text.replace('\\', "\\\\").replace('"', "\\\""))
        }
        NodeKind::List | NodeKind::Tuple => {
            let items: Vec<String> = node.items().iter().map(header_value).collect();
            format!("[{}]", items.join(", "))
        }
        NodeKind::Map => {
            let entries: Vec<String> = node
                .entries()
                .iter()
                .map(|(key, value)| {
                    let key: String = key.text().unwrap_or_else(|| key.python_str());
                    format!("{key} {}", header_value(value))
                })
                .collect();
            format!("({})", entries.join(", "))
        }
        NodeKind::Int { .. } | NodeKind::Other => node.python_str(),
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
