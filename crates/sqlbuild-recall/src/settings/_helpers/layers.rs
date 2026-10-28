//! Layering Recall settings tables and locating the store connection.

use std::path::{Path, PathBuf};

use sqlbuild_config::models::ConfigValue;
use sqlbuild_config::recall::main::recall_section::recall_section;
use sqlbuild_config::recall::models::RecallSection;

use crate::settings::_helpers::documents::{expand_environment, lookup};
use crate::settings::constants::{
    CLICKHOUSE_ADAPTER, CLICKHOUSE_DATABASE_KEY, CLICKHOUSE_DEFAULT_DATABASE,
    CONNECTION_ADAPTER_KEY, DEFAULT_STORE_DIRECTORY, DEFAULT_STORE_FILE_NAME, SQLITE_ADAPTER,
    SQLITE_PATH_KEY,
};
use crate::settings::errors::SettingsError;
use crate::settings::models::{StoreLocation, StorePurpose};

pub(crate) fn section(
    document: Option<&ConfigValue>,
    path: &[&str],
    label: &str,
) -> Result<RecallSection, SettingsError> {
    match lookup(document, path) {
        None => Ok(RecallSection::default()),
        Some(value) => recall_section(value, label).map_err(SettingsError::new),
    }
}

pub(crate) fn overlay(base: RecallSection, layer: RecallSection) -> RecallSection {
    RecallSection {
        enabled: layer.enabled.or(base.enabled),
        write_connection: layer.write_connection.or(base.write_connection),
        read_connection: layer.read_connection.or(base.read_connection),
        retention_days: layer.retention_days.or(base.retention_days),
        shutdown_timeout_ms: layer.shutdown_timeout_ms.or(base.shutdown_timeout_ms),
        diagnostics_min_severity: layer
            .diagnostics_min_severity
            .or(base.diagnostics_min_severity),
        max_output_bytes: layer.max_output_bytes.or(base.max_output_bytes),
        audit_evidence: layer.audit_evidence.or(base.audit_evidence),
    }
}

/// The key and connection the purpose uses from the merged settings; a write connection with no read connection on any layer is a configuration mistake.
pub(crate) fn purpose_connection<'a>(
    effective: &'a RecallSection,
    target: Option<&str>,
    purpose: StorePurpose,
) -> Result<(&'static str, Option<&'a str>), SettingsError> {
    if effective.write_connection.is_some() && effective.read_connection.is_none() {
        let place: String =
            target.map_or_else(String::new, |target| format!(" for target `{target}`"));
        return Err(SettingsError::invalid_configuration(format!(
            "recall.write_connection requires recall.read_connection{place}, the connection \
             `sqb recall` reads history with; set it in [recall], a target's recall table or \
             sqlbuild_local.toml (it may name the same connection)"
        )));
    }
    Ok(match purpose {
        StorePurpose::Record => ("write_connection", effective.write_connection.as_deref()),
        StorePurpose::Read => ("read_connection", effective.read_connection.as_deref()),
    })
}

/// The named connection's entries, local keys overriding project keys.
fn connection_entries(
    documents: [Option<&ConfigValue>; 2],
    name: &str,
) -> Option<Vec<(String, ConfigValue)>> {
    let mut merged: Option<Vec<(String, ConfigValue)>> = None;
    for document in documents {
        let Some(entries) = lookup(document, &["connections", name]).and_then(ConfigValue::as_map)
        else {
            continue;
        };
        let target = merged.get_or_insert_with(Vec::new);
        for (key, value) in entries {
            let ConfigValue::String(key) = key else {
                continue;
            };
            target.retain(|(existing, _)| existing != key);
            target.push((key.clone(), value.clone()));
        }
    }
    merged
}

/// `value` with `${env:...}` expanded in every string it holds.
fn expanded(value: ConfigValue, label: &str) -> Result<ConfigValue, SettingsError> {
    Ok(match value {
        ConfigValue::String(text) => ConfigValue::String(expand_environment(&text, label)?),
        ConfigValue::List(items) => ConfigValue::List(
            items
                .into_iter()
                .map(|item| expanded(item, label))
                .collect::<Result<_, _>>()?,
        ),
        ConfigValue::Map(entries) => ConfigValue::Map(
            entries
                .into_iter()
                .map(|(key, item)| Ok((key, expanded(item, label)?)))
                .collect::<Result<_, SettingsError>>()?,
        ),
        other => other,
    })
}

fn clickhouse_location(
    name: &str,
    entries: Vec<(String, ConfigValue)>,
) -> Result<StoreLocation, SettingsError> {
    let mut config: Vec<(String, ConfigValue)> = Vec::with_capacity(entries.len());
    for (key, value) in entries {
        if key == CONNECTION_ADAPTER_KEY {
            continue;
        }
        let label = format!("connections.{name}.{key}");
        config.push((key, expanded(value, &label)?));
    }
    let database: String = match config
        .iter()
        .find(|(key, _)| key == CLICKHOUSE_DATABASE_KEY)
        .map(|(_, value)| value)
    {
        None => CLICKHOUSE_DEFAULT_DATABASE.to_owned(),
        Some(ConfigValue::String(database)) if !database.trim().is_empty() => {
            database.trim().to_owned()
        }
        Some(_) => {
            return Err(SettingsError::invalid_configuration(format!(
                "connections.{name}.database must name the ClickHouse database Recall writes \
                 to"
            )));
        }
    };
    Ok(StoreLocation::ClickHouse {
        connection: name.to_owned(),
        config,
        database,
    })
}

pub(crate) fn store_location(
    project_dir: &Path,
    documents: [Option<&ConfigValue>; 2],
    (key, connection, project_adapter): (&str, Option<&str>, Option<&str>),
) -> Result<StoreLocation, SettingsError> {
    let Some(name) = connection else {
        return Ok(StoreLocation::Sqlite {
            path: project_dir
                .join(DEFAULT_STORE_DIRECTORY)
                .join(DEFAULT_STORE_FILE_NAME),
        });
    };
    let entries = connection_entries(documents, name).ok_or_else(|| {
        SettingsError::invalid_configuration(format!(
            "recall.{key} names unknown connection '{name}'; define [connections.{name}]"
        ))
    })?;
    let value = |key: &str| {
        entries
            .iter()
            .find(|(candidate, _)| candidate == key)
            .map(|(_, value)| value)
    };
    let adapter: String = match value(CONNECTION_ADAPTER_KEY) {
        Some(ConfigValue::String(adapter)) => adapter.trim().to_owned(),
        Some(_) => {
            return Err(SettingsError::invalid_configuration(format!(
                "connections.{name}.adapter must be a string"
            )));
        }
        None => project_adapter.unwrap_or_default().to_owned(),
    };
    if adapter == CLICKHOUSE_ADAPTER {
        return clickhouse_location(name, entries);
    }
    if adapter != SQLITE_ADAPTER {
        return Ok(StoreLocation::Unsupported {
            connection: name.to_owned(),
            adapter,
        });
    }
    let Some(ConfigValue::String(path)) = value(SQLITE_PATH_KEY) else {
        return Err(SettingsError::invalid_configuration(format!(
            "connections.{name}.path must name the SQLite file Recall writes"
        )));
    };
    let path: PathBuf = PathBuf::from(expand_environment(
        path.trim(),
        &format!("connections.{name}.path"),
    )?);
    Ok(StoreLocation::Sqlite {
        path: if path.is_absolute() {
            path
        } else {
            project_dir.join(path)
        },
    })
}
