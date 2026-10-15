//! Declarative integration loaders: a source's `ingestr` block and top-level `dlt_sources`.

use sqlbuild_core::text::main::python_strip::python_strip;
use sqlbuild_model_config::errors::ConfigError;
use sqlbuild_model_config::types::{AuthoredNode, NodeKind};

use crate::yaml_entries::_helpers::fields::{
    Site, get, optional_mapping, optional_text, reject_unknown_keys, required_text,
    stripped_strings,
};
use crate::yaml_entries::constants::DLT_LOADER_KIND;
use crate::yaml_entries::main::integration_loader_name::integration_loader_name;
use crate::yaml_entries::models::{
    ParsedDltResource, ParsedDltSource, ParsedIngestrConfig, ParsedIntegrationLoader,
    ParsedSourceEntry,
};

const INGESTR_KEYS: [&str; 8] = [
    "columns",
    "extra_args",
    "incremental_key",
    "primary_key",
    "source_table",
    "source_uri",
    "strategy",
    "unique_key",
];
const INGESTR_STRATEGIES: [&str; 5] = [
    "append",
    "delete+insert",
    "merge",
    "replace",
    "truncate+insert",
];
const DLT_GROUP_KEYS: [&str; 5] = ["config", "destination", "resources", "schema", "type"];
const DLT_RESOURCE_KEYS: [&str; 7] = [
    "description",
    "incremental",
    "merge_key",
    "name",
    "primary_key",
    "schema",
    "write_disposition",
];
const FILESYSTEM: &str = "filesystem";
const REST_API: &str = "rest_api";
const SQL_DATABASE: &str = "sql_database";
const BLOCKED_DESTINATION_KEYS: [&str; 3] = ["credentials", "dataset_name", "default_schema_name"];
const RAW_CONFIG_EXCLUDED: [&str; 8] = [
    "name",
    "table",
    "write_disposition",
    "primary_key",
    "merge_key",
    "incremental",
    "schema",
    "description",
];

/// `parse_source_integration_loader`: the source's `ingestr` block, if any.
pub(crate) fn source_integration_loader<N: AuthoredNode>(
    entries: &[(N, N)],
    path: &str,
) -> Result<Option<ParsedIntegrationLoader<N>>, ConfigError> {
    let Some(raw) = get(entries, "ingestr").filter(|value| value.kind() != NodeKind::Null) else {
        return Ok(None);
    };
    if raw.kind() != NodeKind::Map {
        return Err(ConfigError::compile(format!(
            "{path} source 'ingestr' must be a mapping"
        )));
    }
    let config: Vec<(N, N)> = raw.entries();
    let site: Site<'_> = Site {
        path,
        label: "source ingestr",
    };
    reject_unknown_keys(&config, &INGESTR_KEYS, site)?;
    let source_uri: N = required_text(&config, "source_uri", site)?;
    let source_table: N = required_text(&config, "source_table", site)?;
    let strategy: Option<N> = optional_text(&config, "strategy", site)?;
    let incremental_key: Option<N> = optional_text(&config, "incremental_key", site)?;
    let primary_key: Vec<String> = ingestr_strings(&config, "primary_key", path)?;
    let unique_key: Vec<String> = ingestr_strings(&config, "unique_key", path)?;
    if !primary_key.is_empty() && !unique_key.is_empty() {
        return Err(site.error("cannot define both primary_key and unique_key"));
    }
    let columns: Option<N> = optional_text(&config, "columns", site)?;
    let extra_args: Vec<String> = ingestr_strings(&config, "extra_args", path)?;
    if let Some(text) = strategy.as_ref().and_then(AuthoredNode::text)
        && !INGESTR_STRATEGIES.contains(&text.as_str())
    {
        return Err(site.error(&format!(
            "strategy must be one of: {}",
            INGESTR_STRATEGIES.join(", ")
        )));
    }
    Ok(Some(ParsedIntegrationLoader::Ingestr(
        ParsedIngestrConfig {
            source_uri,
            source_table,
            strategy,
            incremental_key,
            primary_key: if primary_key.is_empty() {
                unique_key
            } else {
                primary_key
            },
            columns,
            extra_args,
        },
    )))
}

/// `_optional_ingestr_string_tuple`: one string or a list of strings, each stripped.
fn ingestr_strings<N: AuthoredNode>(
    config: &[(N, N)],
    key: &str,
    path: &str,
) -> Result<Vec<String>, ConfigError> {
    let error = |text: &str| ConfigError::compile(format!("{path} source ingestr '{key}' {text}"));
    let Some(value) = get(config, key).filter(|value| value.kind() != NodeKind::Null) else {
        return Ok(Vec::new());
    };
    stripped_strings(value, error)
}

/// `parse_dlt_sources`: one managed source per resource of each `dlt_sources` group.
pub(crate) fn dlt_sources<N: AuthoredNode>(
    payload: &[(N, N)],
    path: &str,
) -> Result<Vec<ParsedSourceEntry<N>>, ConfigError> {
    let Some(raw_groups) = get(payload, "dlt_sources") else {
        return Ok(Vec::new());
    };
    if raw_groups.kind() != NodeKind::List {
        return Err(ConfigError::compile(format!(
            "{path} dlt_sources must be a list"
        )));
    }
    let mut sources: Vec<ParsedSourceEntry<N>> = Vec::new();
    for (group_index, group) in raw_groups.items().iter().enumerate() {
        if group.kind() != NodeKind::Map {
            return Err(ConfigError::compile(format!(
                "{path} dlt_sources must contain only mappings"
            )));
        }
        sources.extend(dlt_group(&group.entries(), path, group_index)?);
    }
    Ok(sources)
}

fn dlt_group<N: AuthoredNode>(
    group: &[(N, N)],
    path: &str,
    group_index: usize,
) -> Result<Vec<ParsedSourceEntry<N>>, ConfigError> {
    let site: Site<'_> = Site {
        path,
        label: "dlt source",
    };
    reject_unknown_keys(group, &DLT_GROUP_KEYS, site)?;
    let source_type: N = required_text(group, "type", site)?;
    let type_text: String = source_type.text().unwrap_or_default();
    if ![FILESYSTEM, REST_API, SQL_DATABASE].contains(&type_text.as_str()) {
        return Err(site.error("type must be one of: filesystem, rest_api, sql_database"));
    }
    let config: N = match get(group, "config") {
        Some(config) if config.kind() == NodeKind::Map => config.clone(),
        _ => return Err(site.error("config must be a mapping")),
    };
    let destination: Option<N> = optional_mapping(group, "destination", site)?;
    if let Some(destination) = &destination {
        let entries: Vec<(N, N)> = destination.entries();
        for blocked in BLOCKED_DESTINATION_KEYS {
            if get(&entries, blocked).is_some() {
                return Err(site.error(&format!("destination cannot define '{blocked}'")));
            }
        }
    }
    let schema: Option<N> = optional_text(group, "schema", site)?;
    validate_group_config(&type_text, &config.entries(), path)?;
    let resources: Vec<N> = match get(group, "resources") {
        Some(resources) if resources.kind() == NodeKind::List && !resources.items().is_empty() => {
            resources.items()
        }
        _ => return Err(site.error("resources must be a non-empty list")),
    };
    let mut sources: Vec<ParsedSourceEntry<N>> = Vec::with_capacity(resources.len());
    for resource in &resources {
        if resource.kind() != NodeKind::Map {
            return Err(site.error("resources must contain only mappings"));
        }
        let group: DltGroup<'_, N> = DltGroup {
            source_type: &source_type,
            type_text: &type_text,
            schema: schema.as_ref(),
            config: &config,
            destination: destination.as_ref(),
            index: group_index,
        };
        sources.push(dlt_resource(&group, &resource.entries(), path)?);
    }
    Ok(sources)
}

/// What every resource of one dlt source group shares.
struct DltGroup<'a, N> {
    source_type: &'a N,
    type_text: &'a str,
    schema: Option<&'a N>,
    config: &'a N,
    destination: Option<&'a N>,
    index: usize,
}

fn validate_group_config<N: AuthoredNode>(
    source_type: &str,
    config: &[(N, N)],
    path: &str,
) -> Result<(), ConfigError> {
    let error = |text: &str| ConfigError::compile(format!("{path} dlt {text}"));
    let is_text = |value: Option<&N>| value.is_some_and(|value| value.kind() == NodeKind::Str);
    match source_type {
        REST_API => {
            let base_url: bool = get(config, "client")
                .filter(|client| client.kind() == NodeKind::Map)
                .is_some_and(|client| is_text(get(&client.entries(), "base_url")));
            if !base_url {
                return Err(error("rest_api config requires client.base_url"));
            }
        }
        SQL_DATABASE if !is_text(get(config, "credentials")) => {
            return Err(error("sql_database config requires credentials"));
        }
        FILESYSTEM if !is_text(get(config, "bucket_url")) => {
            return Err(error("filesystem config requires bucket_url"));
        }
        _ => {}
    }
    Ok(())
}

fn dlt_resource<N: AuthoredNode>(
    group: &DltGroup<'_, N>,
    resource: &[(N, N)],
    path: &str,
) -> Result<ParsedSourceEntry<N>, ConfigError> {
    let name: N = required_text(
        resource,
        "name",
        Site {
            path,
            label: "dlt resource",
        },
    )?;
    let name_text: String = name.text().unwrap_or_default();
    let error =
        |text: &str| ConfigError::compile(format!("{path} dlt resource '{name_text}' {text}"));
    if get(resource, "write_strategy").is_some() {
        return Err(error("must use dlt write_disposition, not write_strategy"));
    }
    let type_key: &str = match group.type_text {
        FILESYSTEM => "reader",
        REST_API => "endpoint",
        _ => "table",
    };
    let mut allowed: Vec<&str> = DLT_RESOURCE_KEYS.to_vec();
    allowed.push(type_key);
    let typed_label: String = format!("dlt {} resource '{name_text}'", group.type_text);
    reject_unknown_keys(
        resource,
        &allowed,
        Site {
            path,
            label: &typed_label,
        },
    )?;
    let dlt_name: N = dlt_resource_name(group.type_text, resource, path)?;
    let write_disposition: Option<N> = get(resource, "write_disposition").cloned();
    let disposition: Option<String> = write_disposition.as_ref().and_then(AuthoredNode::text);
    if disposition.as_deref() == Some("delete_insert") {
        return Err(error("does not support delete_insert; use a Python loader"));
    }
    let primary_key: Option<N> = get(resource, "primary_key")
        .filter(|value| value.kind() != NodeKind::Null)
        .cloned();
    if disposition.as_deref() == Some("merge") && primary_key.is_none() {
        return Err(error("merge requires primary_key"));
    }
    let resource_label: String = format!("dlt resource '{name_text}'");
    let resource_site: Site<'_> = Site {
        path,
        label: &resource_label,
    };
    let schema: Option<N> = optional_text(resource, "schema", resource_site)?
        .filter(|value| python_truthy_text(value))
        .or_else(|| group.schema.cloned());
    let raw_config: Vec<(N, N)> = if group.type_text == REST_API {
        resource
            .iter()
            .filter(|(key, _)| key.is_text("endpoint"))
            .cloned()
            .collect()
    } else {
        resource
            .iter()
            .filter(|(key, _)| !excluded_from_raw_config(key))
            .cloned()
            .collect()
    };
    let incremental: Option<N> = optional_mapping(resource, "incremental", resource_site)?;
    let description: Option<N> = optional_text(resource, "description", resource_site)?;
    let mut entry: ParsedSourceEntry<N> = ParsedSourceEntry::named(name.clone());
    entry.description = description;
    entry.schema = schema.clone();
    entry.table = Some(name.clone());
    entry.managed = true;
    entry.loader = Some(integration_loader_name(DLT_LOADER_KIND, &name_text));
    entry.integration_loader = Some(ParsedIntegrationLoader::Dlt(Box::new(ParsedDltSource {
        source_type: group.source_type.clone(),
        schema: schema.clone(),
        config: group.config.clone(),
        destination: group.destination.cloned(),
        resource: ParsedDltResource {
            name,
            dlt_name,
            schema,
            raw_config,
            write_disposition,
            primary_key: get(resource, "primary_key").cloned(),
            merge_key: get(resource, "merge_key").cloned(),
            incremental,
        },
        group_index: group.index,
    })));
    Ok(entry)
}

/// Whether `value or other` keeps `value`: a non-empty string is always truthy.
fn python_truthy_text<N: AuthoredNode>(value: &N) -> bool {
    value.with_text(|text| !text.is_empty()).unwrap_or(true)
}

fn dlt_resource_name<N: AuthoredNode>(
    source_type: &str,
    resource: &[(N, N)],
    path: &str,
) -> Result<N, ConfigError> {
    let site = |label| Site { path, label };
    match source_type {
        SQL_DATABASE => required_text(resource, "table", site("dlt sql_database resource")),
        REST_API => {
            let endpoint: Vec<(N, N)> = match get(resource, "endpoint") {
                Some(endpoint) if endpoint.kind() == NodeKind::Map => endpoint.entries(),
                _ => {
                    return Err(ConfigError::compile(format!(
                        "{path} dlt rest_api resource must define endpoint"
                    )));
                }
            };
            if let Some(name) = get(&endpoint, "name")
                && name
                    .with_text(|text| !python_strip(text).is_empty())
                    .unwrap_or(false)
            {
                return Ok(name.clone());
            }
            required_text(resource, "name", site("dlt rest_api resource"))
        }
        _ => required_text(resource, "name", site("dlt filesystem resource")),
    }
}

/// Whether `key` is a resource setting SQLBuild reads itself rather than passing to dlt.
fn excluded_from_raw_config<N: AuthoredNode>(key: &N) -> bool {
    RAW_CONFIG_EXCLUDED
        .iter()
        .any(|excluded| key.is_text(excluded))
}
