use std::path::Path;

use crate::settings::main::resolve_recall_settings::resolve_recall_settings;
use crate::settings::models::{SettingsRequest, StoreLocation};

fn project(files: &[(&str, &str)]) -> tempfile::TempDir {
    let directory = tempfile::tempdir().expect("temporary directory");
    for (name, text) in files {
        std::fs::write(directory.path().join(name), text).expect("write config");
    }
    directory
}

fn request(directory: &Path, target: Option<&str>) -> SettingsRequest {
    SettingsRequest {
        project_dir: directory.to_path_buf(),
        selected_target: target.map(str::to_owned),
    }
}

#[test]
fn given_no_recall_section_when_resolved_then_local_sqlite_is_on_by_default() {
    let directory = project(&[(
        "sqlbuild_project.toml",
        "name = \"shop\"\nadapter = \"duckdb\"\ndefault_target = \"dev\"\n[targets.dev]\nschema = \"analytics\"\n",
    )]);
    let settings = resolve_recall_settings(&request(directory.path(), None)).expect("settings");
    assert!(settings.enabled);
    assert_eq!(settings.target.as_deref(), Some("dev"));
    assert_eq!(
        settings.store,
        StoreLocation::Sqlite {
            path: directory.path().join("logs").join("recall.sqlite3")
        }
    );
    assert_eq!(settings.retention_days, 30);
    assert_eq!(settings.shutdown_timeout_ms, 3000);
    assert_eq!(settings.diagnostics_min_severity, "info");
    assert_eq!(settings.destination_schema.as_deref(), Some("analytics"));
    assert_eq!(settings.project_adapter.as_deref(), Some("duckdb"));
}

#[test]
fn given_layers_when_resolved_then_target_over_local_over_project() {
    let directory = project(&[
        (
            "sqlbuild_project.toml",
            "name = \"shop\"\nadapter = \"duckdb\"\n\
             [recall]\nretention = \"10d\"\nconnection = \"history\"\n\
             [connections.history]\nadapter = \"sqlite\"\npath = \"state/history.sqlite3\"\n\
             [connections.central]\nadapter = \"clickhouse\"\nhost = \"localhost\"\n\
             [targets.dev]\n[targets.dev.recall]\nenabled = false\n\
             [targets.prod]\n[targets.prod.recall]\nconnection = \"central\"\n",
        ),
        (
            "sqlbuild_local.toml",
            "[recall]\nshutdown_timeout = \"1s\"\n[connections.history]\npath = \"/tmp/opencode/elsewhere.sqlite3\"\n",
        ),
    ]);
    let dev = resolve_recall_settings(&request(directory.path(), Some("dev"))).expect("dev");
    assert!(!dev.enabled);
    assert_eq!(dev.retention_days, 10);
    assert_eq!(dev.shutdown_timeout_ms, 1000);
    assert_eq!(
        dev.store,
        StoreLocation::Sqlite {
            path: "/tmp/opencode/elsewhere.sqlite3".into()
        }
    );
    let prod = resolve_recall_settings(&request(directory.path(), Some("prod"))).expect("prod");
    assert!(prod.enabled);
    assert_eq!(
        prod.store,
        StoreLocation::Unsupported {
            connection: "central".to_owned(),
            adapter: "clickhouse".to_owned()
        }
    );
}

#[test]
fn given_invalid_settings_when_resolved_then_the_error_names_the_setting() {
    let unknown = project(&[(
        "sqlbuild_project.toml",
        "name = \"x\"\nadapter = \"duckdb\"\n[recall]\nconnection = \"missing\"\n",
    )]);
    let error = resolve_recall_settings(&request(unknown.path(), None)).expect_err("unknown");
    assert!(
        error.message.contains("unknown connection 'missing'"),
        "{error}"
    );
    let bad = project(&[(
        "sqlbuild_project.toml",
        "name = \"x\"\nadapter = \"duckdb\"\n[targets.dev.recall]\nretention = \"soon\"\n",
    )]);
    let error = resolve_recall_settings(&request(bad.path(), Some("dev"))).expect_err("bad");
    assert!(
        error.message.starts_with("targets.dev.recall.retention"),
        "{error}"
    );
}
