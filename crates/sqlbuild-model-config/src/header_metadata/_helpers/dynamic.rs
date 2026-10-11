//! `dynamic_columns` families read as `parse_dynamic_column_families` reads them.

use crate::errors::ConfigError;
use crate::header_metadata::_helpers::text::non_blank_text;
use crate::header_metadata::constants::{
    DYNAMIC_FAMILY_KEYS, DYNAMIC_NAME_PATTERN_KEY, DYNAMIC_REQUIRED_KEYS,
};
use crate::header_metadata::models::DynamicFamily;
use crate::name_patterns::main::compile_name_pattern::compile_name_pattern;
use crate::types::{AuthoredNode, NodeKind};

/// Who declares the families.
pub(crate) struct DynamicSource<'a> {
    pub(crate) model_name: &'a str,
    pub(crate) path: &'a str,
}

pub(crate) fn dynamic_families<N: AuthoredNode>(
    raw: &N,
    source: &DynamicSource<'_>,
) -> Result<Vec<DynamicFamily>, ConfigError> {
    let model_name: &str = source.model_name;
    if raw.kind() == NodeKind::Null {
        return Ok(Vec::new());
    }
    let entries: Vec<(N, N)> = if raw.kind() == NodeKind::Map {
        raw.entries()
    } else {
        Vec::new()
    };
    if entries.is_empty() {
        return Err(ConfigError::compile(format!(
            "model '{model_name}' dynamic_columns must be a non-empty named block in {}",
            source.path
        )));
    }
    let mut families: Vec<DynamicFamily> = Vec::with_capacity(entries.len());
    for (name, family) in &entries {
        families.push(dynamic_family(name, family, source)?);
    }
    if families.len() > 1 && families.iter().any(|family| family.name_pattern.is_none()) {
        return Err(ConfigError::compile(format!(
            "model '{model_name}' declares multiple dynamic column families; each family requires \
             name_pattern so runtime columns can be classified unambiguously"
        )));
    }
    Ok(families)
}

fn dynamic_family<N: AuthoredNode>(
    name: &N,
    family: &N,
    source: &DynamicSource<'_>,
) -> Result<DynamicFamily, ConfigError> {
    let model_name: &str = source.model_name;
    let Some(name) = name.text().filter(|text| !text.is_empty()) else {
        return Err(ConfigError::compile(format!(
            "model '{model_name}' dynamic column family names must be non-empty strings"
        )));
    };
    if family.kind() != NodeKind::Map {
        return Err(ConfigError::compile(format!(
            "model '{model_name}' dynamic column family '{name}' must be a block"
        )));
    }
    let mut values: Vec<(String, N)> = Vec::new();
    for (key, value) in family.entries() {
        let key: String = key.python_str();
        values.retain(|(existing, _)| *existing != key);
        values.push((key, value));
    }
    let value = |wanted: &str| {
        values
            .iter()
            .find(|(key, _)| key == wanted)
            .map(|(_, value)| value.clone())
    };
    let mut unknown: Vec<&str> = values
        .iter()
        .map(|(key, _)| key.as_str())
        .filter(|key| !DYNAMIC_FAMILY_KEYS.contains(key))
        .collect();
    if !unknown.is_empty() {
        unknown.sort_unstable();
        return Err(ConfigError::compile(format!(
            "model '{model_name}' dynamic column family '{name}' has unsupported keys: {}",
            unknown.join(", ")
        )));
    }
    let required = |key: &str| {
        value(key).as_ref().and_then(non_blank_text).ok_or_else(|| {
            ConfigError::compile(format!(
                "model '{model_name}' dynamic column family '{name}' requires a non-empty {key}"
            ))
        })
    };
    let [pivot_key, value_key, aggregate_key, type_key] = DYNAMIC_REQUIRED_KEYS;
    let pivot_column: String = required(pivot_key)?;
    let value_column: String = required(value_key)?;
    let aggregate: String = required(aggregate_key)?;
    let data_type: String = required(type_key)?;
    let name_pattern: Option<String> = match value(DYNAMIC_NAME_PATTERN_KEY) {
        None => None,
        Some(pattern) if pattern.kind() == NodeKind::Null => None,
        Some(pattern) => Some(non_blank_text(&pattern).ok_or_else(|| {
            ConfigError::compile(format!(
                "model '{model_name}' dynamic column family '{name}' name_pattern must be a \
                 non-empty regular expression"
            ))
        })?),
    };
    if let Some(pattern) = &name_pattern
        && let Err(error) = compile_name_pattern(pattern)
    {
        return Err(ConfigError::compile(format!(
            "model '{model_name}' dynamic column family '{name}' has invalid name_pattern: {error}"
        )));
    }
    Ok(DynamicFamily {
        name,
        pivot_column,
        value_column,
        aggregate: aggregate.to_uppercase(),
        data_type,
        name_pattern,
    })
}
