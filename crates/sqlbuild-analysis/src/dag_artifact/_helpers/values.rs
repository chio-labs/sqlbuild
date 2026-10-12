//! Building artifact values, dropping `None` and empty optional fields, and encoding them.

use sqlbuild_core::json::models::{JsonInteger, JsonValue};

use crate::dag_artifact::constants::REQUIRED_COLLECTION_KEYS;
use crate::dag_artifact::errors::DagArtifactError;
use crate::dag_artifact::models::{DagColumnInput, DagValue};
use crate::dag_artifact::types::DagKey;

/// An object whose keys are all field names.
pub(crate) fn object(entries: Vec<(&str, DagValue)>) -> DagValue {
    DagValue::Object(
        entries
            .into_iter()
            .map(|(key, value)| (Ok(key.to_owned()), value))
            .collect(),
    )
}

/// A string field.
pub(crate) fn text(value: &str) -> DagValue {
    DagValue::String(value.to_owned())
}

/// An optional string field.
pub(crate) fn optional_text(value: Option<&str>) -> DagValue {
    value.map_or(DagValue::Null, text)
}

/// A list of strings.
pub(crate) fn texts<'a>(values: impl IntoIterator<Item = &'a str>) -> DagValue {
    DagValue::Array(values.into_iter().map(text).collect())
}

/// An integer field.
pub(crate) fn integer(value: i64) -> DagValue {
    DagValue::Integer(JsonInteger::from(value))
}

/// A `DagColumn` of an authored column.
pub(crate) fn column(column: &DagColumnInput) -> DagValue {
    object(vec![
        ("name", text(&column.name)),
        ("type", optional_text(column.data_type.as_deref())),
        (
            "nullable",
            column.nullable.map_or(DagValue::Null, DagValue::Bool),
        ),
        ("description", optional_text(column.description.as_deref())),
        ("meta", column.meta.clone()),
    ])
}

/// A `DagColumn` of only a name and type.
pub(crate) fn typed_column((name, data_type): &(String, Option<String>)) -> DagValue {
    object(vec![
        ("name", text(name)),
        ("type", optional_text(data_type.as_deref())),
        ("nullable", DagValue::Null),
        ("description", DagValue::Null),
        ("meta", DagValue::Object(Vec::new())),
    ])
}

fn is_required_collection(key: &DagKey) -> bool {
    key.as_ref()
        .is_ok_and(|key| REQUIRED_COLLECTION_KEYS.contains(&key.as_str()))
}

fn is_empty_collection(value: &DagValue) -> bool {
    match value {
        DagValue::Array(items) => items.is_empty(),
        DagValue::Object(entries) => entries.is_empty(),
        _ => false,
    }
}

/// `_drop_none`: drop `None` fields, then empty optional collections, at every depth.
pub(crate) fn drop_none(value: DagValue) -> DagValue {
    match value {
        DagValue::Array(items) => DagValue::Array(items.into_iter().map(drop_none).collect()),
        DagValue::Object(entries) => DagValue::Object(
            entries
                .into_iter()
                .filter(|(_, item)| *item != DagValue::Null)
                .map(|(key, item)| (key, drop_none(item)))
                .filter(|(key, item)| is_required_collection(key) || !is_empty_collection(item))
                .collect(),
        ),
        other => other,
    }
}

/// The value `json.dumps` encodes, or the `TypeError` it raises first in output order.
pub(crate) fn encoded(value: DagValue) -> Result<JsonValue, DagArtifactError> {
    Ok(match value {
        DagValue::Null => JsonValue::Null,
        DagValue::Bool(flag) => JsonValue::Bool(flag),
        DagValue::Integer(number) => JsonValue::Integer(number),
        DagValue::Float(number) => JsonValue::Float(number),
        DagValue::String(text) => JsonValue::String(text),
        DagValue::Utf16(units) => JsonValue::Utf16(units),
        DagValue::Array(items) => {
            JsonValue::Array(items.into_iter().map(encoded).collect::<Result<_, _>>()?)
        }
        DagValue::Object(entries) => JsonValue::Object(
            entries
                .into_iter()
                .map(|(key, item)| {
                    let key: String = key.map_err(DagArtifactError::Unencodable)?;
                    Ok((key, encoded(item)?))
                })
                .collect::<Result<_, DagArtifactError>>()?,
        ),
        DagValue::Unencodable(message) => return Err(DagArtifactError::Unencodable(message)),
    })
}
