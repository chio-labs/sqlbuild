use crate::models::ConfigValue;
use crate::project::models::{ProjectConfigFile, ProjectSettings};
use tempfile::TempDir;

/// A project directory containing `files`.
pub(super) fn project_directory(files: &[(&str, &str)]) -> TempDir {
    let directory = TempDir::new().expect("temporary directory");
    for (name, contents) in files {
        std::fs::write(directory.path().join(name), contents).expect("write project file");
    }
    directory
}

pub(super) fn minimal_project() -> ProjectConfigFile {
    ProjectConfigFile {
        name: "orders".to_owned(),
        adapter: "duckdb".to_owned(),
        default_target: None,
        settings: ProjectSettings {
            sql_analysis: true,
            require_sql_analysis: false,
        },
        enforce_placement: true,
        enforce_explicit_references: true,
        vars: vec![],
        path_defaults: vec![],
        target_names: vec![],
    }
}

pub(super) fn configured_project() -> ProjectConfigFile {
    ProjectConfigFile {
        default_target: Some("dev".to_owned()),
        settings: ProjectSettings {
            sql_analysis: false,
            require_sql_analysis: true,
        },
        enforce_placement: false,
        vars: vec![("region".to_owned(), "eu".to_owned())],
        path_defaults: vec![(
            "staging".to_owned(),
            ConfigValue::Map(vec![(
                ConfigValue::String("materialized".to_owned()),
                ConfigValue::String("view".to_owned()),
            )]),
        )],
        target_names: vec!["dev".to_owned(), "prod".to_owned()],
        ..minimal_project()
    }
}
