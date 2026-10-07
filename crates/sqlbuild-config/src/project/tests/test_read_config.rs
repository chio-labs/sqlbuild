use crate::errors::ConfigErrorKind;
use crate::project::main::read_local_config::read_local_config;
use crate::project::main::read_project_config::read_project_config;
use crate::project::models::{LocalConfigFile, ProjectSettings};
use crate::project::tests::helpers::{configured_project, minimal_project, project_directory};
use crate::project::tests::test_types::{LocalConfigTestCase, ProjectConfigTestCase};

const PROJECT: &str = "sqlbuild_project.toml";
const LOCAL: &str = "sqlbuild_local.toml";

#[test]
fn given_project_files_when_reading_then_discovery_fields_match_python_loader() {
    let test_cases = [
        ProjectConfigTestCase {
            description: "defaults apply and strings are stripped",
            files: &[(PROJECT, "name = ' orders '\nadapter = \"duckdb\"\n")],
            expected_config: Ok(minimal_project()),
        },
        ProjectConfigTestCase {
            description: "discovery sections are read in document order",
            files: &[(
                PROJECT,
                "name = 'orders'\nadapter = 'duckdb'\ndefault_target = 'dev'\n\
                 [settings]\nsql_analysis = false\nrequire_sql_analysis = true\n\
                 [scopes]\nenforce_placement = false\n[vars]\nregion = 'eu'\n\
                 [path_defaults.staging]\nmaterialized = 'view'\n\
                 [targets.dev]\n[targets.prod]\n",
            )],
            expected_config: Ok(configured_project()),
        },
        ProjectConfigTestCase {
            description: "legacy sql_validation sets SQL analysis",
            files: &[(
                PROJECT,
                "name = 'orders'\nadapter = 'duckdb'\n[settings]\nsql_validation = false\n",
            )],
            expected_config: Ok(crate::project::models::ProjectConfigFile {
                settings: ProjectSettings {
                    sql_analysis: false,
                    require_sql_analysis: false,
                },
                ..minimal_project()
            }),
        },
        ProjectConfigTestCase {
            description: "conflicting analysis keys are rejected",
            files: &[(
                PROJECT,
                "name = 'orders'\nadapter = 'duckdb'\n[settings]\nsql_analysis = true\nsql_validation = false\n",
            )],
            expected_config: Err(ConfigErrorKind::InvalidField),
        },
        ProjectConfigTestCase {
            description: "blank name is rejected",
            files: &[(PROJECT, "name = '  '\nadapter = 'duckdb'\n")],
            expected_config: Err(ConfigErrorKind::InvalidField),
        },
        ProjectConfigTestCase {
            description: "non-string var is rejected",
            files: &[(
                PROJECT,
                "name = 'orders'\nadapter = 'duckdb'\n[vars]\nlimit = 3\n",
            )],
            expected_config: Err(ConfigErrorKind::InvalidField),
        },
        ProjectConfigTestCase {
            description: "legacy YAML project file is rejected",
            files: &[("sqlbuild_project.yml", "name: orders\n")],
            expected_config: Err(ConfigErrorKind::InvalidField),
        },
        ProjectConfigTestCase {
            description: "missing project file",
            files: &[],
            expected_config: Err(ConfigErrorKind::Missing),
        },
    ];
    for test_case in test_cases {
        let directory = project_directory(test_case.files);
        let actual = read_project_config(directory.path()).map_err(|error| error.kind);
        assert_eq!(
            actual, test_case.expected_config,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_local_files_when_reading_then_overrides_match_python_loader() {
    let test_cases = [
        LocalConfigTestCase {
            description: "absent local file reads as defaults",
            files: &[],
            expected_config: Ok(LocalConfigFile::default()),
        },
        LocalConfigTestCase {
            description: "local overrides are read",
            files: &[(
                LOCAL,
                "target = 'dev'\n[settings]\nsql_validation = false\n[vars]\nregion = 'us'\n[targets.dev]\n",
            )],
            expected_config: Ok(LocalConfigFile {
                target: Some("dev".to_owned()),
                adapter: None,
                sql_analysis: Some(false),
                vars: vec![("region".to_owned(), "us".to_owned())],
                target_names: vec!["dev".to_owned()],
            }),
        },
        LocalConfigTestCase {
            description: "legacy YAML local file is rejected",
            files: &[("sqlbuild_local.yml", "target: dev\n")],
            expected_config: Err(ConfigErrorKind::InvalidField),
        },
    ];
    for test_case in test_cases {
        let directory = project_directory(test_case.files);
        let actual = read_local_config(directory.path()).map_err(|error| error.kind);
        assert_eq!(
            actual, test_case.expected_config,
            "{}",
            test_case.description
        );
    }
}
