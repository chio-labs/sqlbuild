//! One seed declaration of a schema YAML file, and its CSV settings.

use sqlbuild_model_config::errors::ConfigError;
use sqlbuild_model_config::header_metadata::main::parse_audit_list::parse_audit_list;
use sqlbuild_model_config::types::{AuthoredNode, NodeKind};

use crate::yaml_entries::_helpers::columns::yaml_columns;
use crate::yaml_entries::_helpers::fields::{
    Site, get, optional_mapping, optional_text, optional_texts, reject_unknown_keys, required_text,
};
use crate::yaml_entries::models::{
    ParsedCsvSettings, ParsedNaValues, ParsedSeedEntry, ParsedYamlColumn,
};

const SEED_ENTRY_KEYS: [&str; 9] = [
    "name",
    "description",
    "database",
    "schema",
    "meta",
    "csv_settings",
    "columns",
    "tags",
    "audits",
];
const SEED_COLUMN_KEYS: [&str; 6] = ["name", "type", "nullable", "description", "meta", "audits"];
const CSV_SETTING_KEYS: [&str; 9] = [
    "delimiter",
    "quotechar",
    "doublequote",
    "escapechar",
    "skipinitialspace",
    "lineterminator",
    "encoding",
    "na_values",
    "keep_default_na",
];
const CSV_STRING_SETTINGS: [&str; 5] = [
    "delimiter",
    "quotechar",
    "escapechar",
    "lineterminator",
    "encoding",
];
const CSV_BOOL_SETTINGS: [&str; 3] = ["doublequote", "skipinitialspace", "keep_default_na"];

/// `_parse_named_mapping_list`.
pub(crate) fn mapping_list<N: AuthoredNode>(
    value: &N,
    path: &str,
    label: &str,
) -> Result<Vec<N>, ConfigError> {
    if value.kind() != NodeKind::List {
        return Err(ConfigError::compile(format!(
            "{path} {label} must be a list"
        )));
    }
    let items: Vec<N> = value.items();
    if items.iter().any(|item| item.kind() != NodeKind::Map) {
        return Err(ConfigError::compile(format!(
            "{path} {label} must contain only mappings"
        )));
    }
    Ok(items)
}

pub(crate) fn seed_entry<N: AuthoredNode>(
    entries: &[(N, N)],
    path: &str,
) -> Result<ParsedSeedEntry<N>, ConfigError> {
    let site: Site<'_> = Site {
        path,
        label: "seed",
    };
    reject_unknown_keys(entries, &SEED_ENTRY_KEYS, site)?;
    let columns: Vec<ParsedYamlColumn<N>> = yaml_columns(entries, site, Some(&SEED_COLUMN_KEYS))?;
    if columns.is_empty() {
        return Err(site.error("must declare at least one column"));
    }
    for column in &columns {
        if column.column_type.is_none() {
            return Err(site.error(&format!(
                "column '{}' must define non-empty string 'type'",
                column.name.python_str()
            )));
        }
    }
    Ok(ParsedSeedEntry {
        name: required_text(entries, "name", site)?,
        description: optional_text(entries, "description", site)?,
        database: optional_text(entries, "database", site)?,
        schema: optional_text(entries, "schema", site)?,
        meta: optional_mapping(entries, "meta", site)?,
        tags: optional_texts(entries, "tags", site)?,
        csv_settings: csv_settings(entries, path)?,
        columns,
        audits: parse_audit_list(get(entries, "audits"), path, "seed", false)?,
    })
}

fn csv_settings<N: AuthoredNode>(
    entries: &[(N, N)],
    path: &str,
) -> Result<Option<ParsedCsvSettings<N>>, ConfigError> {
    let raw: N = match get(entries, "csv_settings") {
        None => return Ok(None),
        Some(value) if value.kind() == NodeKind::Null => return Ok(None),
        Some(value) => value.clone(),
    };
    if raw.kind() != NodeKind::Map {
        return Err(ConfigError::compile(format!(
            "{path} seed 'csv_settings' must be a mapping"
        )));
    }
    let settings: Vec<(N, N)> = raw.entries();
    let mut unknown: Vec<String> = settings
        .iter()
        .filter(|(key, _)| !csv_setting_key(key))
        .map(|(key, _)| key.python_str())
        .collect();
    if !unknown.is_empty() {
        unknown.sort();
        return Err(ConfigError::compile(format!(
            "{path} seed 'csv_settings' has unknown keys: {}",
            unknown.join(", ")
        )));
    }
    let set = |key: &str| get(&settings, key).filter(|value| value.kind() != NodeKind::Null);
    for key in CSV_STRING_SETTINGS {
        if set(key).is_some_and(|value| value.kind() != NodeKind::Str) {
            return Err(ConfigError::compile(format!(
                "{path} seed csv_settings '{key}' must be a string"
            )));
        }
    }
    for key in CSV_BOOL_SETTINGS {
        if set(key).is_some_and(|value| !matches!(value.kind(), NodeKind::Bool(_))) {
            return Err(ConfigError::compile(format!(
                "{path} seed csv_settings '{key}' must be a boolean"
            )));
        }
    }
    Ok(Some(ParsedCsvSettings {
        delimiter: set("delimiter").cloned(),
        quotechar: set("quotechar").cloned(),
        doublequote: set("doublequote").cloned(),
        escapechar: set("escapechar").cloned(),
        skipinitialspace: set("skipinitialspace").cloned(),
        lineterminator: set("lineterminator").cloned(),
        encoding: set("encoding").cloned(),
        na_values: na_values(set("na_values"), path)?,
        keep_default_na: set("keep_default_na").cloned(),
    }))
}

fn na_values<N: AuthoredNode>(
    raw: Option<&N>,
    path: &str,
) -> Result<Option<ParsedNaValues<N>>, ConfigError> {
    let Some(raw) = raw else {
        return Ok(None);
    };
    match raw.kind() {
        NodeKind::List => Ok(Some(ParsedNaValues::List(na_scalars(raw, path)?))),
        NodeKind::Map => {
            let mut columns: Vec<(N, Vec<N>)> = Vec::new();
            for (column, values) in raw.entries() {
                if values.kind() != NodeKind::List {
                    return Err(ConfigError::compile(format!(
                        "{path} seed csv_settings 'na_values' mapping values must be lists"
                    )));
                }
                columns.push((column, na_scalars(&values, path)?));
            }
            Ok(Some(ParsedNaValues::PerColumn(columns)))
        }
        _ => Err(ConfigError::compile(format!(
            "{path} seed csv_settings 'na_values' must be a list or mapping"
        ))),
    }
}

fn na_scalars<N: AuthoredNode>(list: &N, path: &str) -> Result<Vec<N>, ConfigError> {
    let items: Vec<N> = list.items();
    for item in &items {
        let scalar: bool = matches!(
            item.kind(),
            NodeKind::Null | NodeKind::Str | NodeKind::Bool(_) | NodeKind::Int { .. }
        );
        if !scalar {
            return Err(ConfigError::compile(format!(
                "{path} seed csv_settings 'na_values' entries must be strings, integers, \
                 booleans, or null"
            )));
        }
    }
    Ok(items)
}

fn csv_setting_key<N: AuthoredNode>(key: &N) -> bool {
    CSV_SETTING_KEYS.iter().any(|allowed| key.is_text(allowed))
}
