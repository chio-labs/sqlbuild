//! Size, depth and key bounds of integration values and the allowlisted metadata mappings.

use crate::integration_results::_helpers::values::{field, one_of, text_length};
use crate::integration_results::constants::{
    MAX_COLLECTION_ITEMS, MAX_IDENTIFIER_CHARS, MAX_METADATA_BYTES, MAX_NESTING_DEPTH,
    MAX_RECORD_BYTES, MAX_STRING_CHARS, MAXIMUM_START_ACTIONS, MAXIMUM_START_INPUT_KEYS,
    MAXIMUM_START_KEYS, MAXIMUM_START_NULLABLE_KEY, MAXIMUM_START_REQUIRED_KEYS,
    MAXIMUM_START_STRUCTURED_KEYS,
};
use crate::integration_results::errors::IntegrationRecordError;
use crate::json::main::dumps::dumps;
use crate::json::models::{JsonDialect, JsonValue, StdlibJsonOptions};

/// `validate_json_value`: reject non-finite, deep, oversized or badly keyed values.
pub(crate) fn validate_json_value(
    value: &JsonValue,
    depth: usize,
) -> Result<(), IntegrationRecordError> {
    if depth > MAX_NESTING_DEPTH {
        return Err(IntegrationRecordError::new(
            "integration JSON exceeds nesting limit",
        ));
    }
    match value {
        JsonValue::Null | JsonValue::Bool(_) | JsonValue::Integer(_) => Ok(()),
        JsonValue::Float(number) if !number.is_finite() => Err(IntegrationRecordError::new(
            "integration JSON numbers must be finite",
        )),
        JsonValue::Float(_) => Ok(()),
        JsonValue::String(_) | JsonValue::Utf16(_) => {
            if text_length(value).unwrap_or(0) > MAX_STRING_CHARS {
                return Err(IntegrationRecordError::new(
                    "integration JSON string exceeds size limit",
                ));
            }
            Ok(())
        }
        JsonValue::Object(entries) => {
            if entries.len() > MAX_COLLECTION_ITEMS {
                return Err(IntegrationRecordError::new(
                    "integration JSON object exceeds item limit",
                ));
            }
            for (key, item) in entries {
                let length: usize = key.chars().count();
                if length == 0 || length > MAX_IDENTIFIER_CHARS {
                    return Err(IntegrationRecordError::new(
                        "integration JSON object key is invalid",
                    ));
                }
                validate_json_value(item, depth + 1)?;
            }
            Ok(())
        }
        JsonValue::Array(items) => {
            if items.len() > MAX_COLLECTION_ITEMS {
                return Err(IntegrationRecordError::new(
                    "integration JSON array exceeds item limit",
                ));
            }
            items
                .iter()
                .try_for_each(|item| validate_json_value(item, depth + 1))
        }
    }
}

/// `encode_integration_json`: strict compact ASCII JSON within the metadata or record limit.
pub(crate) fn encode(value: &JsonValue, record: bool) -> Result<String, IntegrationRecordError> {
    validate_json_value(value, 0)?;
    let options: StdlibJsonOptions = StdlibJsonOptions {
        allow_nan: false,
        ..StdlibJsonOptions::new(None).with_separators(",", ":")
    };
    let Ok(encoded) = dumps(value, &JsonDialect::Stdlib(options)) else {
        return Err(IntegrationRecordError::new(
            "integration value is not strict JSON",
        ));
    };
    let limit: usize = if record {
        MAX_RECORD_BYTES
    } else {
        MAX_METADATA_BYTES
    };
    if encoded.len() > limit {
        return Err(IntegrationRecordError::new(
            "integration JSON exceeds size limit",
        ));
    }
    Ok(encoded)
}

fn nested_keys_allowed(value: &JsonValue, allowed: &[&str]) -> bool {
    match value {
        JsonValue::Object(entries) => entries.iter().all(|(key, item)| {
            allowed.contains(&key.as_str()) && nested_keys_allowed(item, allowed)
        }),
        JsonValue::Array(items) => items.iter().all(|item| nested_keys_allowed(item, allowed)),
        _ => true,
    }
}

/// `validate_allowlisted_mapping`: an object whose keys, at every depth, are allowlisted.
pub(crate) fn allowlisted_mapping(
    value: &JsonValue,
    field_name: &str,
    allowed: &[&str],
) -> Result<(), IntegrationRecordError> {
    let JsonValue::Object(entries) = value else {
        return Err(IntegrationRecordError::new(format!(
            "integration {field_name} must be an object"
        )));
    };
    if entries
        .iter()
        .any(|(key, _)| !allowed.contains(&key.as_str()))
    {
        return Err(IntegrationRecordError::new(format!(
            "integration {field_name} contains unknown fields"
        )));
    }
    let _ = encode(value, false)?;
    if !nested_keys_allowed(value, allowed) {
        return Err(IntegrationRecordError::new(format!(
            "integration {field_name} contains unknown fields"
        )));
    }
    Ok(())
}

/// Whether the object has exactly the given keys.
pub(crate) fn has_exactly(entries: &[(String, JsonValue)], keys: &[&str]) -> bool {
    entries.len() == keys.len() && keys.iter().all(|key| has_key(entries, key))
}

/// Whether the object has the key.
pub(crate) fn has_key(entries: &[(String, JsonValue)], key: &str) -> bool {
    entries.iter().any(|(name, _)| name == key)
}

/// `validate_maximum_start_safety`: empty, or the canonical maximum-start structure.
pub(crate) fn maximum_start_safety(value: &JsonValue) -> Result<(), IntegrationRecordError> {
    allowlisted_mapping(value, "maximum_start_safety", &MAXIMUM_START_KEYS)?;
    let JsonValue::Object(entries) = value else {
        return Ok(());
    };
    if entries.is_empty() {
        return Ok(());
    }
    if !has_exactly(entries, &MAXIMUM_START_REQUIRED_KEYS) {
        return Err(IntegrationRecordError::new(
            "integration maximum_start_safety must use the canonical structure",
        ));
    }
    if !one_of(field(entries, "action"), &MAXIMUM_START_ACTIONS) {
        return Err(IntegrationRecordError::new(
            "integration maximum_start_safety action is unsupported",
        ));
    }
    for name in MAXIMUM_START_REQUIRED_KEYS {
        if MAXIMUM_START_STRUCTURED_KEYS.contains(&name) {
            continue;
        }
        let item: &JsonValue = field(entries, name);
        let nullable: bool = name == MAXIMUM_START_NULLABLE_KEY && matches!(item, JsonValue::Null);
        if text_length(item).is_none() && !nullable {
            return Err(IntegrationRecordError::new(format!(
                "integration maximum_start_safety {name} has an invalid type"
            )));
        }
    }
    let input: &JsonValue = field(entries, "input");
    let JsonValue::Object(input) = input else {
        return Err(IntegrationRecordError::new(
            "integration maximum_start_safety input must use the canonical structure",
        ));
    };
    if !has_exactly(input, &MAXIMUM_START_INPUT_KEYS) {
        return Err(IntegrationRecordError::new(
            "integration maximum_start_safety input must use the canonical structure",
        ));
    }
    if input
        .iter()
        .any(|(_, item)| text_length(item).is_none_or(|length| length == 0))
    {
        return Err(IntegrationRecordError::new(
            "integration maximum_start_safety input values must be non-empty strings",
        ));
    }
    Ok(())
}
