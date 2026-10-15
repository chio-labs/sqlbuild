use crate::dbt_profile::errors::DbtProfileError;
use crate::dbt_profile::main::dbt_init_project_toml::dbt_init_project_toml;
use crate::dbt_profile::main::dbt_profile_outputs::dbt_profile_outputs;
use crate::dbt_profile::main::dbt_project_metadata::dbt_project_metadata;
use crate::dbt_profile::main::normalize_dbt_profile::normalize_dbt_profile;
use crate::dbt_profile::main::select_dbt_profile_target::select_dbt_profile_target;
use crate::dbt_profile::models::{
    ConnectionKey, ConnectionSource, DbtProfileOutputs, DbtProjectMetadata, DbtYamlValue,
    LoadedDbtProfile, NormalizedProfile, ProfileValue,
};
use crate::dbt_profile::tests::helpers::{
    YAML_MAPPING, entry, init_config, loaded_profile, profile_outputs, text, yaml_text,
};
use crate::dbt_profile::tests::test_types::{
    InitTomlTestCase, NormalizeTestCase, ProfileOutputsTestCase, ProjectMetadataTestCase,
    SelectTargetTestCase,
};

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

#[test]
fn given_dbt_project_values_when_reading_metadata_then_strings_are_stripped_and_required() {
    let test_cases = [
        ProjectMetadataTestCase {
            description: "padded values are stripped and target-path defaults",
            values: [
                yaml_text(" shop "),
                yaml_text("orders "),
                DbtYamlValue::Null,
            ],
            expected_result: Ok(DbtProjectMetadata {
                project_name: "shop".to_owned(),
                profile_name: "orders".to_owned(),
                target_path: "target".to_owned(),
            }),
        },
        ProjectMetadataTestCase {
            description: "a blank name is rejected before the profile",
            values: [yaml_text("  "), DbtYamlValue::Null, DbtYamlValue::Null],
            expected_result: Err(DbtProfileError(
                "dbt_project.yml must define non-empty string 'name'".to_owned(),
            )),
        },
        ProjectMetadataTestCase {
            description: "a non-string profile is rejected",
            values: [yaml_text("shop"), DbtYamlValue::Other, DbtYamlValue::Null],
            expected_result: Err(DbtProfileError(
                "dbt_project.yml must define non-empty string 'profile'".to_owned(),
            )),
        },
        ProjectMetadataTestCase {
            description: "a mapping target-path is rejected",
            values: [yaml_text("shop"), yaml_text("orders"), YAML_MAPPING],
            expected_result: Err(DbtProfileError(
                "dbt_project.yml target-path must be a non-empty string".to_owned(),
            )),
        },
    ];
    for test_case in test_cases {
        let [name, profile, target_path] = &test_case.values;
        assert_eq!(
            dbt_project_metadata("dbt_project.yml", (name, profile, target_path)),
            test_case.expected_result,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_loaded_profile_when_validating_outputs_then_names_and_target_follow_dbt_rules() {
    let test_cases = [
        ProfileOutputsTestCase {
            description: "a repeated stripped name keeps its first place and last output",
            loaded: loaded_profile(
                vec![
                    (yaml_text(" dev"), YAML_MAPPING),
                    (yaml_text("prod"), YAML_MAPPING),
                    (yaml_text("dev "), YAML_MAPPING),
                ],
                yaml_text(" dev "),
            ),
            expected_result: Ok(DbtProfileOutputs {
                name: "shop".to_owned(),
                default_target: Some("dev".to_owned()),
                outputs: vec![("dev".to_owned(), 2), ("prod".to_owned(), 1)],
            }),
        },
        ProfileOutputsTestCase {
            description: "a profile that is not a mapping is undefined",
            loaded: LoadedDbtProfile {
                profile: yaml_text("shop"),
                outputs: DbtYamlValue::Null,
                output_entries: Vec::new(),
                target: DbtYamlValue::Null,
            },
            expected_result: Err(DbtProfileError(
                "profiles.yml does not define dbt profile 'shop'".to_owned(),
            )),
        },
        ProfileOutputsTestCase {
            description: "empty outputs are rejected",
            loaded: loaded_profile(Vec::new(), DbtYamlValue::Null),
            expected_result: Err(DbtProfileError(
                "dbt profile 'shop' must define non-empty outputs".to_owned(),
            )),
        },
        ProfileOutputsTestCase {
            description: "a non-string output name is invalid",
            loaded: loaded_profile(
                vec![(DbtYamlValue::Other, YAML_MAPPING)],
                DbtYamlValue::Null,
            ),
            expected_result: Err(DbtProfileError(
                "dbt profile 'shop' contains an invalid output name".to_owned(),
            )),
        },
        ProfileOutputsTestCase {
            description: "a scalar output names its unstripped key",
            loaded: loaded_profile(
                vec![(yaml_text(" dev"), yaml_text("duckdb"))],
                DbtYamlValue::Null,
            ),
            expected_result: Err(DbtProfileError(
                "dbt profile 'shop' output ' dev' must be a mapping".to_owned(),
            )),
        },
        ProfileOutputsTestCase {
            description: "a blank target is rejected after the outputs",
            loaded: loaded_profile(vec![(yaml_text("dev"), YAML_MAPPING)], yaml_text(" ")),
            expected_result: Err(DbtProfileError(
                "dbt profile 'shop' target must be a non-empty string".to_owned(),
            )),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            dbt_profile_outputs("profiles.yml", "shop", &test_case.loaded),
            test_case.expected_result,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_profile_outputs_when_selecting_target_then_requested_or_default_output_is_chosen() {
    let test_cases = [
        SelectTargetTestCase {
            description: "the requested target wins over the default",
            profile: profile_outputs(Some("dev"), &["dev", "prod"]),
            requested: Some("prod"),
            expected_result: Ok(("prod".to_owned(), 1)),
        },
        SelectTargetTestCase {
            description: "an empty request falls back to the default",
            profile: profile_outputs(Some("dev"), &["dev", "prod"]),
            requested: Some(""),
            expected_result: Ok(("dev".to_owned(), 0)),
        },
        SelectTargetTestCase {
            description: "no request and no default asks for --target",
            profile: profile_outputs(None, &["dev"]),
            requested: None,
            expected_result: Err(DbtProfileError(
                "dbt profile 'shop' does not define a default target; pass --target".to_owned(),
            )),
        },
        SelectTargetTestCase {
            description: "an unknown target lists the sorted targets",
            profile: profile_outputs(Some("qa"), &["zeta", "alpha", "Beta"]),
            requested: None,
            expected_result: Err(DbtProfileError(
                "dbt profile 'shop' does not define target 'qa'. Available targets: Beta, alpha, zeta"
                    .to_owned(),
            )),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            select_dbt_profile_target(&test_case.profile, test_case.requested),
            test_case.expected_result,
            "{}",
            test_case.description
        );
    }
}
