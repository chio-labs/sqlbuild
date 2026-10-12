//! Python's `parse_loaded_sources_yml`: the source declarations of one loaded sources YAML file.

use sqlbuild_model_config::errors::ConfigError;
use sqlbuild_model_config::header_metadata::main::parse_audit_list::parse_audit_list;
use sqlbuild_model_config::types::{AuthoredNode, NodeKind};

use crate::yaml_entries::_helpers::fields::{
    Site, get, optional_bool, optional_mapping, optional_text, reject_unknown_keys, required_text,
};
use crate::yaml_entries::_helpers::freshness::freshness;
use crate::yaml_entries::_helpers::integrations::{
    dlt_sources, integration_loader_name, source_integration_loader,
};
use crate::yaml_entries::main::parse_schema_document::yaml_columns;
use crate::yaml_entries::models::{ParsedIntegrationLoader, ParsedSourceEntry, ParsedYamlColumn};

const FILE_KEYS: [&str; 2] = ["sources", "dlt_sources"];
const ENTRY_KEYS: [&str; 18] = [
    "audits",
    "columns",
    "contract",
    "cursor_column",
    "database",
    "description",
    "expression",
    "freshness",
    "ingestr",
    "load_batch_size",
    "managed",
    "meta",
    "name",
    "schema",
    "table",
    "type_enforcement",
    "unique_key",
    "write_strategy",
];
const COLUMN_KEYS: [&str; 6] = ["audits", "description", "meta", "name", "nullable", "type"];
const CONTRACT_POLICIES: [&str; 2] = ["none", "enforced"];
const WRITE_STRATEGIES: [&str; 4] = ["append", "delete_insert", "merge", "table"];
const APPEND: &str = "append";
const DELETE_INSERT: &str = "delete_insert";
const MERGE: &str = "merge";
const TABLE: &str = "table";

/// Parse a loaded sources document: its `sources`, then the managed sources of `dlt_sources`.
pub fn parse_sources_document<N: AuthoredNode>(
    loaded: &N,
    path: &str,
) -> Result<Vec<ParsedSourceEntry<N>>, ConfigError> {
    let payload: Vec<(N, N)> = match loaded.kind() {
        NodeKind::Null => Vec::new(),
        NodeKind::Map => loaded.entries(),
        _ => {
            return Err(ConfigError::compile(format!(
                "{path} must contain a top-level mapping"
            )));
        }
    };
    reject_unknown_keys(
        &payload,
        &FILE_KEYS,
        Site {
            path,
            label: "sources file",
        },
    )?;
    let mut sources: Vec<ParsedSourceEntry<N>> = Vec::new();
    if let Some(raw) = get(&payload, "sources") {
        if raw.kind() != NodeKind::List {
            return Err(ConfigError::compile(format!(
                "{path} sources must be a list"
            )));
        }
        for item in raw.items() {
            if item.kind() != NodeKind::Map {
                return Err(ConfigError::compile(format!(
                    "{path} sources must contain only mappings"
                )));
            }
            sources.push(source_entry(&item.entries(), path)?);
        }
    }
    sources.extend(dlt_sources(&payload, path)?);
    Ok(sources)
}

fn source_entry<N: AuthoredNode>(
    entry: &[(N, N)],
    path: &str,
) -> Result<ParsedSourceEntry<N>, ConfigError> {
    let site: Site<'_> = Site {
        path,
        label: "source",
    };
    let columns: Vec<ParsedYamlColumn<N>> = yaml_columns(entry, site, Some(&COLUMN_KEYS))?;
    let authored_enforcement: Option<bool> = optional_bool(entry, "type_enforcement", site)?
        .map(|node| node.kind() == NodeKind::Bool(true));
    let contract: Option<N> = optional_text(entry, "contract", site)?;
    if contract
        .as_ref()
        .and_then(AuthoredNode::text)
        .is_some_and(|text| !CONTRACT_POLICIES.contains(&text.as_str()))
    {
        return Err(site.error("'contract' must be one of: enforced, none"));
    }
    let expression: Option<N> = optional_text(entry, "expression", site)?;
    let type_enforcement: Option<bool> = authored_enforcement.or_else(|| {
        columns
            .iter()
            .any(|column| column.column_type.is_some())
            .then_some(true)
    });
    if get(entry, "loader").is_some() {
        return Err(site.error(
            "'loader' is not supported; use managed: true and name the terminal loader after \
             the source",
        ));
    }
    reject_unknown_keys(entry, &ENTRY_KEYS, site)?;
    let name: N = required_text(entry, "name", site)?;
    let name_text: String = name.text().unwrap_or_default();
    let integration_loader: Option<ParsedIntegrationLoader<N>> =
        source_integration_loader(entry, path)?;
    let mut managed: bool = optional_bool(entry, "managed", site)?
        .is_some_and(|node| node.kind() == NodeKind::Bool(true));
    let mut loader: Option<String> = managed.then(|| name_text.clone());
    if loader.is_none()
        && let Some(integration) = &integration_loader
    {
        loader = Some(integration_loader_name(integration.kind(), &name_text));
        managed = true;
    }
    let mut parsed: ParsedSourceEntry<N> = ParsedSourceEntry::named(name);
    parsed.database = optional_text(entry, "database", site)?;
    parsed.schema = optional_text(entry, "schema", site)?;
    parsed.table = optional_text(entry, "table", site)?;
    parsed.managed = managed;
    parsed.loader = loader;
    parsed.integration_loader = integration_loader;
    parsed.freshness = freshness(entry, &columns, path)?;
    parsed.write_strategy = write_strategy(entry, site)?;
    parsed.load_batch_size = positive_int(entry, "load_batch_size", path)?;
    parsed.cursor_column = optional_text(entry, "cursor_column", site)?;
    parsed.unique_key = unique_key(entry, path)?;
    parsed.expression = expression;
    parsed.description = optional_text(entry, "description", site)?;
    parsed.type_enforcement = type_enforcement;
    parsed.contract = contract;
    parsed.meta = optional_mapping(entry, "meta", site)?;
    parsed.columns = columns;
    parsed.audits = parse_audit_list(get(entry, "audits"), path, "source", false)?;
    validate_source(&parsed, &name_text, path)?;
    Ok(parsed)
}

fn write_strategy<N: AuthoredNode>(
    entry: &[(N, N)],
    site: Site<'_>,
) -> Result<Option<&'static str>, ConfigError> {
    let Some(text) = optional_text(entry, "write_strategy", site)?.and_then(|node| node.text())
    else {
        return Ok(None);
    };
    WRITE_STRATEGIES
        .iter()
        .copied()
        .find(|strategy| *strategy == text)
        .map(Some)
        .ok_or_else(|| {
            site.error(&format!(
                "write_strategy must be one of: {}",
                WRITE_STRATEGIES.join(", ")
            ))
        })
}

fn positive_int<N: AuthoredNode>(
    entry: &[(N, N)],
    key: &str,
    path: &str,
) -> Result<Option<N>, ConfigError> {
    let Some(value) = get(entry, key).filter(|value| value.kind() != NodeKind::Null) else {
        return Ok(None);
    };
    match value.kind() {
        NodeKind::Int { negative: false } if value.python_str() != "0" => Ok(Some(value.clone())),
        _ => Err(ConfigError::compile(format!(
            "{path} source '{key}' must be a positive integer"
        ))),
    }
}

fn unique_key<N: AuthoredNode>(entry: &[(N, N)], path: &str) -> Result<Vec<String>, ConfigError> {
    let error = |text: &str| ConfigError::compile(format!("{path} source 'unique_key' {text}"));
    let Some(value) = get(entry, "unique_key").filter(|value| value.kind() != NodeKind::Null)
    else {
        return Ok(Vec::new());
    };
    match value.kind() {
        NodeKind::Str => {
            let stripped: String = value.text().unwrap_or_default().trim().to_owned();
            if stripped.is_empty() {
                return Err(error("must be non-empty"));
            }
            Ok(vec![stripped])
        }
        NodeKind::List => {
            let keys: Vec<String> = value
                .items()
                .iter()
                .map(|item| {
                    item.text()
                        .map(|text| text.trim().to_owned())
                        .filter(|text| !text.is_empty())
                        .ok_or_else(|| error("must contain only non-empty strings"))
                })
                .collect::<Result<_, _>>()?;
            if keys.is_empty() {
                return Err(error("must be non-empty"));
            }
            Ok(keys)
        }
        _ => Err(error("must be a string or list")),
    }
}

/// `_validate_source_entry`.
fn validate_source<N: AuthoredNode>(
    entry: &ParsedSourceEntry<N>,
    name: &str,
    path: &str,
) -> Result<(), ConfigError> {
    let error = |text: &str| ConfigError::compile(format!("{path} source '{name}' {text}"));
    let relation_keys: Vec<&str> = [
        ("database", &entry.database),
        ("schema", &entry.schema),
        ("table", &entry.table),
    ]
    .into_iter()
    .filter(|(_, value)| value.is_some())
    .map(|(key, _)| key)
    .collect();
    if entry.expression.is_some() && !relation_keys.is_empty() {
        return Err(error(&format!(
            "cannot define expression with {}",
            relation_keys.join(", ")
        )));
    }
    if entry.expression.is_some()
        && entry.type_enforcement == Some(true)
        && !entry
            .columns
            .iter()
            .any(|column| column.column_type.is_some())
    {
        return Err(error(
            "uses expression with type_enforcement but has no typed columns",
        ));
    }
    if let Some(integration) = &entry.integration_loader {
        let kind: &str = integration.kind();
        if entry.loader.as_deref() != Some(integration_loader_name(kind, name).as_str()) {
            return Err(error(&format!("cannot override loader for {kind}")));
        }
        if entry.write_strategy.is_some() {
            return Err(error(&format!("cannot define write_strategy with {kind}")));
        }
    }
    let strategy: Option<&str> = entry.write_strategy;
    let has_unique_key: bool = !entry.unique_key.is_empty();
    let has_cursor: bool = entry.cursor_column.is_some();
    if strategy.is_some() && entry.loader.is_none() {
        return Err(error("defines write_strategy but is not managed"));
    }
    if strategy == Some(APPEND) && has_unique_key {
        return Err(error(
            "unique_key is not supported with write_strategy append",
        ));
    }
    if strategy == Some(MERGE) && !has_unique_key {
        return Err(error("write_strategy merge requires unique_key"));
    }
    if strategy == Some(TABLE) && has_cursor {
        return Err(error(
            "cursor_column is not supported with write_strategy table",
        ));
    }
    if strategy == Some(TABLE) && has_unique_key {
        return Err(error(
            "unique_key is not supported with write_strategy table",
        ));
    }
    if strategy == Some(DELETE_INSERT) && !has_cursor {
        return Err(error("write_strategy delete_insert requires cursor_column"));
    }
    if strategy == Some(DELETE_INSERT) && has_unique_key {
        return Err(error(
            "unique_key is not supported with write_strategy delete_insert",
        ));
    }
    if has_cursor && !matches!(strategy, Some(APPEND | DELETE_INSERT | MERGE)) {
        return Err(error(
            "cursor_column requires write_strategy append, delete_insert, or merge",
        ));
    }
    if has_unique_key && strategy != Some(MERGE) {
        return Err(error("unique_key requires write_strategy merge"));
    }
    Ok(())
}
