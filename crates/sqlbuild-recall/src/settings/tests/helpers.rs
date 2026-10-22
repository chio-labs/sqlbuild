use std::path::PathBuf;

use sqlbuild_config::models::ConfigValue;

use crate::settings::main::resolve_recall_settings::resolve_recall_settings;
use crate::settings::models::{RecallSettings, SettingsRequest, StoreLocation, StorePurpose};

/// The placeholder project directory resolved paths are reported under.
pub(crate) const PROJECT: &str = "<project>";

/// Settings resolved for a project holding `files`, debug-printed with its directory as `PROJECT`.
pub(crate) fn resolved(
    files: &[(&str, &str)],
    target: Option<&str>,
    purpose: StorePurpose,
) -> Result<String, String> {
    let directory = tempfile::tempdir().expect("a temporary directory can be created");
    for (name, text) in files {
        std::fs::write(directory.path().join(name), text).expect("test files can be written");
    }
    let request = SettingsRequest {
        project_dir: directory.path().to_path_buf(),
        selected_target: target.map(str::to_owned),
        purpose,
    };
    let project: String = directory.path().to_string_lossy().into_owned();
    resolve_recall_settings(&request)
        .map(|settings| format!("{settings:?}").replace(&project, PROJECT))
        .map_err(|error| error.message)
}

/// The built-in local store of the project.
pub(crate) fn local_store() -> StoreLocation {
    StoreLocation::Sqlite {
        path: PathBuf::from(PROJECT).join("logs").join("recall.sqlite3"),
    }
}

/// The `central` ClickHouse store of the layered test project.
pub(crate) fn central_store() -> StoreLocation {
    StoreLocation::ClickHouse {
        connection: "central".to_owned(),
        config: vec![
            (
                "host".to_owned(),
                ConfigValue::String("localhost".to_owned()),
            ),
            (
                "database".to_owned(),
                ConfigValue::String("observability".to_owned()),
            ),
            (
                "password".to_owned(),
                ConfigValue::String("secret".to_owned()),
            ),
        ],
        database: "observability".to_owned(),
    }
}

/// The default settings for project `shop` on the duckdb adapter.
pub(crate) fn defaults() -> RecallSettings {
    RecallSettings {
        enabled: true,
        target: None,
        store: local_store(),
        write_connection: None,
        read_connection: None,
        retention_days: 30,
        shutdown_timeout_ms: 3000,
        diagnostics_min_severity: "info".to_owned(),
        max_output_bytes: Some(2 * 1024 * 1024),
        project_name: Some("shop".to_owned()),
        project_adapter: Some("duckdb".to_owned()),
        destination_database: None,
        destination_schema: None,
    }
}

/// Why settings for a project holding `files` do not resolve: the message and whether it is a configuration mistake.
pub(crate) fn resolution_error(
    files: &[(&str, &str)],
    target: Option<&str>,
    purpose: StorePurpose,
) -> Option<(String, bool)> {
    let directory = tempfile::tempdir().expect("a temporary directory can be created");
    for (name, text) in files {
        std::fs::write(directory.path().join(name), text).expect("test files can be written");
    }
    let request = SettingsRequest {
        project_dir: directory.path().to_path_buf(),
        selected_target: target.map(str::to_owned),
        purpose,
    };
    resolve_recall_settings(&request)
        .err()
        .map(|error| (error.message, error.invalid_configuration))
}
