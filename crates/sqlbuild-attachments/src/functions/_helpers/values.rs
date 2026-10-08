//! Python's header value checks: non-empty stripped strings, maps and string lists.

use sqlbuild_core::text::main::python_strip::python_strip;

use crate::functions::models::{HeaderValue, NamedType};

/// Python's `TABLE_FUNCTION_RETURN_KEYS`.
pub(crate) const TABLE_RETURN_KEY: &str = "table";

/// `value.strip()` when `value` is a string that is not blank.
pub(crate) fn stripped_text(value: Option<&HeaderValue>) -> Option<String> {
    match value? {
        HeaderValue::Text(text) if !python_strip(text).is_empty() => {
            Some(python_strip(text).to_owned())
        }
        _ => None,
    }
}

/// Named types of a map of non-blank strings; None where Python raises.
pub(crate) fn named_types(entries: &[(HeaderValue, HeaderValue)]) -> Option<Vec<NamedType>> {
    let mut named: Vec<NamedType> = Vec::with_capacity(entries.len());
    for (key, value) in entries {
        let HeaderValue::Text(raw_name) = key else {
            return None;
        };
        named.push(NamedType {
            raw_name: raw_name.clone(),
            name: stripped_text(Some(key))?,
            type_text: stripped_text(Some(value))?,
        });
    }
    Some(named)
}

/// Stripped entries of an optional list or tuple of non-blank strings.
pub(crate) fn stripped_list(value: Option<&HeaderValue>) -> Option<Vec<String>> {
    match value {
        None => Some(Vec::new()),
        Some(HeaderValue::Sequence(items)) => {
            let mut entries: Vec<String> = Vec::with_capacity(items.len());
            for item in items {
                entries.push(stripped_text(Some(item))?);
            }
            Some(entries)
        }
        Some(_) => None,
    }
}

/// An optional string description, stripped.
pub(crate) fn description(value: Option<&HeaderValue>) -> Option<Option<String>> {
    match value {
        None => Some(None),
        Some(HeaderValue::Text(text)) => Some(Some(python_strip(text).to_owned())),
        Some(_) => None,
    }
}

/// The header value under `key`.
pub(crate) fn lookup<'header>(
    header: &'header [(String, HeaderValue)],
    key: &str,
) -> Option<&'header HeaderValue> {
    header
        .iter()
        .find(|(name, _)| name == key)
        .map(|(_, value)| value)
}
