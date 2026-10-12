//! Building manifest values as Python dicts, lists and strings.

use crate::python_values::main::text_key::text_key;
use crate::python_values::models::{PythonKey, PythonValue};

/// A dict of field names, later duplicate keys replacing earlier values in place.
pub(crate) fn object(entries: Vec<(&str, PythonValue)>) -> PythonValue {
    let mut fields: Vec<(PythonKey, PythonValue)> = Vec::new();
    for (key, value) in entries {
        fields = inserted(fields, text_key(key), value);
    }
    PythonValue::Object(fields)
}

/// `d[key] = value`: replace the value in place, or append the entry.
pub(crate) fn inserted(
    entries: Vec<(PythonKey, PythonValue)>,
    key: PythonKey,
    value: PythonValue,
) -> Vec<(PythonKey, PythonValue)> {
    let mut entries: Vec<(PythonKey, PythonValue)> = entries;
    match entries.iter_mut().find(|(existing, _)| *existing == key) {
        Some(entry) => entry.1 = value,
        None => entries.push((key, value)),
    }
    entries
}

/// A dict of `str` keys built entry by entry, as a dict comprehension or `update` builds it.
pub(crate) fn keyed(entries: Vec<(String, PythonValue)>) -> PythonValue {
    let mut fields: Vec<(PythonKey, PythonValue)> = Vec::new();
    for (key, value) in entries {
        fields = inserted(fields, text_key(&key), value);
    }
    PythonValue::Object(fields)
}

/// A string.
pub(crate) fn text(value: &str) -> PythonValue {
    PythonValue::String(value.to_owned())
}

/// A string or `None`.
pub(crate) fn optional_text(value: Option<&str>) -> PythonValue {
    value.map_or(PythonValue::Null, text)
}

/// `value or ""`.
pub(crate) fn text_or_empty(value: Option<&str>) -> PythonValue {
    text(value.unwrap_or_default())
}

/// A list of strings.
pub(crate) fn texts<'a>(values: impl IntoIterator<Item = &'a str>) -> PythonValue {
    PythonValue::Array(values.into_iter().map(text).collect())
}

/// An empty dict.
pub(crate) fn empty_object() -> PythonValue {
    PythonValue::Object(Vec::new())
}

/// An empty list.
pub(crate) fn empty_array() -> PythonValue {
    PythonValue::Array(Vec::new())
}

/// `0.0`.
pub(crate) fn zero_float() -> PythonValue {
    PythonValue::Float(0.0)
}

/// `{"show": True, "node_color": None}`.
pub(crate) fn docs() -> PythonValue {
    object(vec![
        ("show", PythonValue::Bool(true)),
        ("node_color", PythonValue::Null),
    ])
}
