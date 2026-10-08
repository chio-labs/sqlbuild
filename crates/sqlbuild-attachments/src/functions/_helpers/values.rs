//! Python's header value checks: non-empty stripped strings, maps and string lists.

use sqlbuild_core::text::main::python_strip::python_strip;

use crate::functions::errors::NamedTypeError;
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

/// Named types of a map of non-blank strings, and Python's error after the ones before it.
pub(crate) fn named_types(
    entries: &[(HeaderValue, HeaderValue)],
) -> (Vec<NamedType>, Option<NamedTypeError>) {
    let mut named: Vec<NamedType> = Vec::with_capacity(entries.len());
    for (key, value) in entries {
        let (HeaderValue::Text(raw_name), Some(name)) = (key, stripped_text(Some(key))) else {
            return (named, Some(NamedTypeError::InvalidName));
        };
        let Some(type_text) = stripped_text(Some(value)) else {
            return (named, Some(NamedTypeError::MissingType(raw_name.clone())));
        };
        named.push(NamedType {
            raw_name: raw_name.clone(),
            name,
            type_text,
        });
    }
    (named, None)
}

/// Stripped list entries; `Err(true)` for a non-sequence, `Err(false)` for a blank entry.
pub(crate) fn stripped_list(value: Option<&HeaderValue>) -> Result<Vec<String>, bool> {
    match value {
        None => Ok(Vec::new()),
        Some(HeaderValue::Sequence(items)) => {
            let mut entries: Vec<String> = Vec::with_capacity(items.len());
            for item in items {
                entries.push(stripped_text(Some(item)).ok_or(false)?);
            }
            Ok(entries)
        }
        Some(_) => Err(true),
    }
}

/// An optional string description, stripped; None when it is not a string.
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
