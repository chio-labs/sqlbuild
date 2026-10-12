//! Python's `parse_loaded_schema_yml`: the seed declarations of one loaded schema YAML file.

use sqlbuild_model_config::errors::ConfigError;
use sqlbuild_model_config::header_metadata::main::parse_audit_list::parse_audit_list;
use sqlbuild_model_config::types::{AuthoredNode, NodeKind};

use crate::yaml_entries::_helpers::fields::{
    Site, get, optional_bool, optional_mapping, optional_text, optional_texts, reject_unknown_keys,
    required_text, truthy,
};
use crate::yaml_entries::models::{
    ParsedCsvSettings, ParsedNaValues, ParsedSeedEntry, ParsedYamlColumn,
};

const SEED_FILE_KEYS: [&str; 1] = ["seeds"];
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
const NOT_NULL_AUDIT: &str = "not_null";

/// Parse a loaded schema document; `in_seeds_directory` is whether `seeds` is among the path's parts.
pub fn parse_schema_document<N: AuthoredNode>(
    loaded: &N,
    path: &str,
    in_seeds_directory: bool,
) -> Result<Vec<ParsedSeedEntry<N>>, ConfigError> {
    let entries: Vec<(N, N)> = match loaded.kind() {
        NodeKind::Null => Vec::new(),
        NodeKind::Map => loaded.entries(),
        _ => {
            return Err(ConfigError::compile(format!(
                "{path} must contain a top-level mapping"
            )));
        }
    };
    let file: Site<'_> = Site { path, label: "" };
    if let Some(models) = get(&entries, "models") {
        if truthy(models) {
            return Err(ConfigError::compile(format!(
                "{path} declares model metadata in 'models', but model metadata must live in the \
                 model file MODEL(...). Move description, columns, and audits into the model \
                 header."
            )));
        }
        mapping_list(models, path, "models")?;
    }
    let seeds: Option<&N> = get(&entries, "seeds");
    if seeds.is_some_and(truthy) && !in_seeds_directory {
        return Err(ConfigError::compile(format!(
            "{path} declares seeds, but seed declarations must live under seeds/**/*.yml"
        )));
    }
    if in_seeds_directory {
        reject_unknown_keys(
            &entries,
            &SEED_FILE_KEYS,
            Site {
                label: "seed file",
                ..file
            },
        )?;
    }
    let Some(seeds) = seeds else {
        return Ok(Vec::new());
    };
    mapping_list(seeds, path, "seeds")?
        .iter()
        .map(|seed| seed_entry(&seed.entries(), path))
        .collect()
}

/// `_parse_named_mapping_list`.
fn mapping_list<N: AuthoredNode>(
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

fn seed_entry<N: AuthoredNode>(
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

/// `_parse_columns` of a seed or source entry.
pub(crate) fn yaml_columns<N: AuthoredNode>(
    entries: &[(N, N)],
    site: Site<'_>,
    allowed: Option<&[&str]>,
) -> Result<Vec<ParsedYamlColumn<N>>, ConfigError> {
    let Some(raw) = get(entries, "columns") else {
        return Ok(Vec::new());
    };
    if raw.kind() != NodeKind::List {
        return Err(site.error("columns must be a list"));
    }
    let label: String = format!("{} column", site.label);
    let column_site: Site<'_> = Site {
        path: site.path,
        label: &label,
    };
    let mut columns: Vec<ParsedYamlColumn<N>> = Vec::new();
    for raw_column in raw.items() {
        if raw_column.kind() != NodeKind::Map {
            return Err(site.error("columns must contain only mappings"));
        }
        let column: Vec<(N, N)> = raw_column.entries();
        if let Some(allowed) = allowed {
            reject_unknown_keys(&column, allowed, column_site)?;
        }
        let name: N = required_text(&column, "name", column_site)?;
        let nullable: Option<N> = optional_bool(&column, "nullable", column_site)?;
        let audits = parse_audit_list(get(&column, "audits"), site.path, &label, false)?;
        let declares_nullable: bool = nullable
            .as_ref()
            .is_some_and(|value| value.kind() == NodeKind::Bool(true));
        if declares_nullable
            && audits
                .iter()
                .any(|audit| audit.definition_name.is_text(NOT_NULL_AUDIT))
        {
            return Err(ConfigError::compile(format!(
                "{} column '{}' cannot set nullable = true and audit not_null",
                site.path,
                name.python_str()
            )));
        }
        columns.push(ParsedYamlColumn {
            name,
            column_type: optional_text(&column, "type", column_site)?,
            nullable,
            description: optional_text(&column, "description", column_site)?,
            meta: optional_mapping(&column, "meta", column_site)?,
            audits,
        });
    }
    Ok(columns)
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
        .filter(|(key, _)| !CSV_SETTING_KEYS.iter().any(|allowed| key.is_text(allowed)))
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
