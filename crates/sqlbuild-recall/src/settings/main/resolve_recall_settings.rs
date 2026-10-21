//! `resolve_recall_settings`: the effective Recall settings of one invocation.

use sqlbuild_config::models::ConfigValue;
use sqlbuild_config::recall::constants::RECALL_SECTION;

use crate::settings::_helpers::documents::{read_document, string_at};
use crate::settings::_helpers::layers::{overlay, purpose_connection, section, store_location};
use crate::settings::constants::{
    DEFAULT_DIAGNOSTICS_MIN_SEVERITY, DEFAULT_RETENTION_DAYS, DEFAULT_SHUTDOWN_TIMEOUT_MS,
    LOCAL_FILE_NAME, PROJECT_FILE_NAME,
};
use crate::settings::errors::SettingsError;
use crate::settings::models::{RecallSettings, SettingsRequest};

/// The effective settings: `targets.<t>.recall` over `[recall]` over the built-in local store, local configuration over project configuration at each level. Only the connection of the request's purpose is resolved, so a machine holding only the writer's or only the reader's credentials resolves its own side.
pub fn resolve_recall_settings(request: &SettingsRequest) -> Result<RecallSettings, SettingsError> {
    let project = read_document(&request.project_dir.join(PROJECT_FILE_NAME))?;
    let local = read_document(&request.project_dir.join(LOCAL_FILE_NAME))?;
    let documents: [Option<&ConfigValue>; 2] = [project.as_ref(), local.as_ref()];
    let target: Option<String> = request
        .selected_target
        .clone()
        .or_else(|| string_at(local.as_ref(), &["target"]))
        .or_else(|| string_at(project.as_ref(), &["default_target"]));
    let mut effective = section(project.as_ref(), &[RECALL_SECTION], RECALL_SECTION)?;
    effective = overlay(
        effective,
        section(local.as_ref(), &[RECALL_SECTION], RECALL_SECTION)?,
    );
    if let Some(target) = target.as_deref() {
        let label = format!("targets.{target}.recall");
        for document in documents {
            effective = overlay(
                effective,
                section(document, &["targets", target, RECALL_SECTION], &label)?,
            );
        }
    }
    let project_adapter: Option<String> = string_at(local.as_ref(), &["adapter"])
        .or_else(|| string_at(project.as_ref(), &["adapter"]));
    let target_field = |key: &str| -> Option<String> {
        let target = target.as_deref()?;
        string_at(local.as_ref(), &["targets", target, key])
            .or_else(|| string_at(project.as_ref(), &["targets", target, key]))
    };
    let (key, connection): (&str, Option<&str>) =
        purpose_connection(&effective, target.as_deref(), request.purpose)?;
    let store = store_location(
        &request.project_dir,
        documents,
        (key, connection, project_adapter.as_deref()),
    )?;
    let max_output_bytes: Option<u64> = match effective.max_output_bytes {
        Some(0) => None,
        Some(bytes) => Some(bytes),
        None => store.default_max_output_bytes(),
    };
    Ok(RecallSettings {
        enabled: effective.enabled.unwrap_or(true),
        target: target.clone(),
        store,
        write_connection: effective.write_connection,
        read_connection: effective.read_connection,
        retention_days: effective.retention_days.unwrap_or(DEFAULT_RETENTION_DAYS),
        shutdown_timeout_ms: effective
            .shutdown_timeout_ms
            .unwrap_or(DEFAULT_SHUTDOWN_TIMEOUT_MS),
        diagnostics_min_severity: effective
            .diagnostics_min_severity
            .unwrap_or_else(|| DEFAULT_DIAGNOSTICS_MIN_SEVERITY.to_owned()),
        max_output_bytes,
        project_name: string_at(project.as_ref(), &["name"]),
        project_adapter,
        destination_database: target_field("database"),
        destination_schema: target_field("schema"),
    })
}
