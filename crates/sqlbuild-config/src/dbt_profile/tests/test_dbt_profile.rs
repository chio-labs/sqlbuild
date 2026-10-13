use crate::dbt_profile::errors::DbtProfileError;
use crate::dbt_profile::main::dbt_init_project_toml::dbt_init_project_toml;
use crate::dbt_profile::main::normalize_dbt_profile::normalize_dbt_profile;
use crate::dbt_profile::models::{
    ConnectionKey, ConnectionSource, NormalizedProfile, ProfileValue,
};
use crate::dbt_profile::tests::helpers::{entry, init_config, text};
use crate::dbt_profile::tests::test_types::{InitTomlTestCase, NormalizeTestCase};

#[test]
fn given_rendered_profile_outputs_when_normalizing_then_matches_python_rules() {
    let test_cases = [
        NormalizeTestCase {
            description: "duckdb falls back from a null path to memory and warns on plugins",
            entries: vec![
                text("type", "duckdb"),
                entry("path", ProfileValue::Null),
                entry("plugins", ProfileValue::Other),
                entry("extensions", ProfileValue::Other),
                text("schema", ""),
            ],
            expected_result: Ok(NormalizedProfile {
                adapter: "duckdb",
                connection: vec![
                    (ConnectionKey::Name("database"), ConnectionSource::Text(":memory:")),
                    (ConnectionKey::Name("extensions"), ConnectionSource::Entry(3)),
                ],
                target_schema: Some(String::new()),
                target_database: None,
                warnings: vec![
                    "dbt-duckdb profile fields are not applied by SQLBuild yet: plugins".to_owned(),
                ],
            }),
        },
        NormalizeTestCase {
            description: "postgres prefers a present dbname even when it is null",
            entries: vec![
                text("type", "postgres"),
                entry("dbname", ProfileValue::Null),
                text("database", "db"),
                text("pass", "pw"),
                text("host", "h"),
            ],
            expected_result: Ok(NormalizedProfile {
                adapter: "postgres",
                connection: vec![
                    (ConnectionKey::Name("host"), ConnectionSource::Entry(4)),
                    (ConnectionKey::Name("password"), ConnectionSource::Entry(3)),
                ],
                target_schema: None,
                target_database: None,
                warnings: Vec::new(),
            }),
        },
        NormalizeTestCase {
            description: "databricks defaults the catalog",
            entries: vec![text("type", "databricks"), text("host", "h"), text("schema", "s")],
            expected_result: Ok(NormalizedProfile {
                adapter: "databricks",
                connection: vec![
                    (ConnectionKey::Name("server_hostname"), ConnectionSource::Entry(1)),
                    (ConnectionKey::Name("catalog"), ConnectionSource::Text("hive_metastore")),
                    (ConnectionKey::Name("schema"), ConnectionSource::Entry(2)),
                ],
                target_schema: Some("s".to_owned()),
                target_database: Some("hive_metastore".to_owned()),
                warnings: Vec::new(),
            }),
        },
        NormalizeTestCase {
            description: "sqlserver rejects windows logins",
            entries: vec![text("type", "sqlserver"), entry("windows_login", ProfileValue::Bool(true))],
            expected_result: Err(DbtProfileError(
                "dbt SQL Server Windows authentication is not supported by SQLBuild dbt-profile normalization yet".to_owned(),
            )),
        },
        NormalizeTestCase {
            description: "missing type",
            entries: vec![entry("type", ProfileValue::Other)],
            expected_result: Err(DbtProfileError(
                "dbt profile type '<missing>' is not supported by SQLBuild dbt-profile connection resolution yet. Currently supported: bigquery, databricks, duckdb, postgres, snowflake, sqlserver".to_owned(),
            )),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            normalize_dbt_profile(&test_case.entries),
            test_case.expected_result,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_init_values_when_writing_project_toml_then_keys_and_strings_are_escaped() {
    let test_cases = [
        InitTomlTestCase {
            description: "plain target with a schema",
            config: init_config("dev", Some("main")),
            expected_toml: "name = \"analytics\"\nadapter = \"duckdb\"\ndefault_target = \"dev\"\n\n[dbt]\nproject_dir = \"../dbt_project\"\nprofiles_dir = \"C:\\\\profiles\"\ntarget_path = \"../dbt_project/target\"\ntarget = \"dev\"\n\n[connections.dev_dbt_profile]\nsource = \"dbt_profile\"\nprofile = \"ana\\\"lytics\"\ntarget = \"dev\"\n\n[targets.dev]\nconnection = \"dev_dbt_profile\"\nschema = \"main\"\n",
        },
        InitTomlTestCase {
            description: "dotted target is quoted",
            config: init_config("a.b", None),
            expected_toml: "name = \"analytics\"\nadapter = \"duckdb\"\ndefault_target = \"a.b\"\n\n[dbt]\nproject_dir = \"../dbt_project\"\nprofiles_dir = \"C:\\\\profiles\"\ntarget_path = \"../dbt_project/target\"\ntarget = \"a.b\"\n\n[connections.\"a.b_dbt_profile\"]\nsource = \"dbt_profile\"\nprofile = \"ana\\\"lytics\"\ntarget = \"a.b\"\n\n[targets.\"a.b\"]\nconnection = \"a.b_dbt_profile\"\n",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            dbt_init_project_toml(&test_case.config),
            test_case.expected_toml,
            "{}",
            test_case.description
        );
    }
}
