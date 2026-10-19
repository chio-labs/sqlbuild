use sqlbuild_config::models::ConfigValue;

use crate::settings::models::{RecallSettings, StoreLocation};
use crate::settings::tests::helpers::{defaults, resolved};
use crate::settings::tests::test_types::{ResolveErrorTestCase, ResolveTestCase};

const DEFAULT_PROJECT: &[(&str, &str)] = &[(
    "sqlbuild_project.toml",
    "name = \"shop\"\nadapter = \"duckdb\"\ndefault_target = \"dev\"\n[targets.dev]\nschema = \"analytics\"\n",
)];

const LAYERED_PROJECT: &[(&str, &str)] = &[
    (
        "sqlbuild_project.toml",
        "name = \"shop\"\nadapter = \"duckdb\"\n\
         [recall]\nretention = \"10d\"\nconnection = \"history\"\n\
         [connections.history]\nadapter = \"sqlite\"\npath = \"state/history.sqlite3\"\n\
         [connections.central]\nadapter = \"clickhouse\"\nhost = \"localhost\"\n\
         database = \"observability\"\npassword = \"secret\"\n\
         [connections.other]\nadapter = \"postgres\"\nhost = \"localhost\"\n\
         [targets.dev]\n[targets.dev.recall]\nenabled = false\n\
         [targets.prod]\n[targets.prod.recall]\nconnection = \"central\"\n\
         [targets.capped]\n[targets.capped.recall]\nconnection = \"central\"\n\
         max_output_bytes = 4096\n\
         [targets.qa]\n[targets.qa.recall]\nconnection = \"other\"\n",
    ),
    (
        "sqlbuild_local.toml",
        "[recall]\nshutdown_timeout = \"1s\"\n[connections.history]\npath = \"/tmp/opencode/elsewhere.sqlite3\"\n",
    ),
];

const OUTPUT_LIMIT_PROJECT: &[(&str, &str)] = &[(
    "sqlbuild_project.toml",
    "name = \"shop\"\nadapter = \"duckdb\"\n[recall]\nmax_output_bytes = 0\n\
     [targets.dev]\n[targets.dev.recall]\nmax_output_bytes = 8388608\n[targets.prod]\n",
)];

#[test]
fn given_project_layers_when_resolved_then_target_over_local_over_project_over_defaults() {
    let test_cases = [
        ResolveTestCase {
            description: "without a recall section local SQLite is on by default",
            files: DEFAULT_PROJECT,
            target: None,
            expected_settings: RecallSettings {
                target: Some("dev".to_owned()),
                destination_schema: Some("analytics".to_owned()),
                ..defaults()
            },
        },
        ResolveTestCase {
            description: "the target disables recall and the local file moves the store",
            files: LAYERED_PROJECT,
            target: Some("dev"),
            expected_settings: RecallSettings {
                enabled: false,
                target: Some("dev".to_owned()),
                store: StoreLocation::Sqlite {
                    path: "/tmp/opencode/elsewhere.sqlite3".into(),
                },
                connection: Some("history".to_owned()),
                retention_days: 10,
                shutdown_timeout_ms: 1000,
                ..defaults()
            },
        },
        ResolveTestCase {
            description: "a ClickHouse connection keeps its options and records all output by default",
            files: LAYERED_PROJECT,
            target: Some("prod"),
            expected_settings: RecallSettings {
                target: Some("prod".to_owned()),
                store: StoreLocation::ClickHouse {
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
                },
                connection: Some("central".to_owned()),
                retention_days: 10,
                shutdown_timeout_ms: 1000,
                max_output_bytes: None,
                ..defaults()
            },
        },
        ResolveTestCase {
            description: "a configured output limit applies to a ClickHouse store",
            files: LAYERED_PROJECT,
            target: Some("capped"),
            expected_settings: RecallSettings {
                target: Some("capped".to_owned()),
                store: StoreLocation::ClickHouse {
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
                },
                connection: Some("central".to_owned()),
                retention_days: 10,
                shutdown_timeout_ms: 1000,
                max_output_bytes: Some(4096),
                ..defaults()
            },
        },
        ResolveTestCase {
            description: "a target raises the output limit over the project's unlimited one",
            files: OUTPUT_LIMIT_PROJECT,
            target: Some("dev"),
            expected_settings: RecallSettings {
                target: Some("dev".to_owned()),
                max_output_bytes: Some(8_388_608),
                ..defaults()
            },
        },
        ResolveTestCase {
            description: "zero records all output",
            files: OUTPUT_LIMIT_PROJECT,
            target: Some("prod"),
            expected_settings: RecallSettings {
                target: Some("prod".to_owned()),
                max_output_bytes: None,
                ..defaults()
            },
        },
        ResolveTestCase {
            description: "a connection on another adapter is reported as unsupported",
            files: LAYERED_PROJECT,
            target: Some("qa"),
            expected_settings: RecallSettings {
                target: Some("qa".to_owned()),
                store: StoreLocation::Unsupported {
                    connection: "other".to_owned(),
                    adapter: "postgres".to_owned(),
                },
                connection: Some("other".to_owned()),
                retention_days: 10,
                shutdown_timeout_ms: 1000,
                max_output_bytes: None,
                ..defaults()
            },
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            resolved(test_case.files, test_case.target),
            Ok(format!("{:?}", test_case.expected_settings)),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_invalid_settings_when_resolved_then_the_error_names_the_setting() {
    let test_cases = [
        ResolveErrorTestCase {
            description: "unknown connections are named",
            files: &[(
                "sqlbuild_project.toml",
                "name = \"x\"\nadapter = \"duckdb\"\n[recall]\nconnection = \"missing\"\n",
            )],
            target: None,
            expected_message_fragment: "unknown connection 'missing'",
        },
        ResolveErrorTestCase {
            description: "target settings are named with their path",
            files: &[(
                "sqlbuild_project.toml",
                "name = \"x\"\nadapter = \"duckdb\"\n[targets.dev.recall]\nretention = \"soon\"\n",
            )],
            target: Some("dev"),
            expected_message_fragment: "targets.dev.recall.retention",
        },
        ResolveErrorTestCase {
            description: "an unset environment reference in a ClickHouse connection is named",
            files: &[(
                "sqlbuild_project.toml",
                "name = \"x\"\nadapter = \"duckdb\"\n[recall]\nconnection = \"central\"\n\
                 [connections.central]\nadapter = \"clickhouse\"\n\
                 password = \"${env:SQLBUILD_RECALL_UNSET_FOR_TEST}\"\n",
            )],
            target: None,
            expected_message_fragment: "connections.central.password references unset",
        },
    ];

    for test_case in test_cases {
        let message: String =
            resolved(test_case.files, test_case.target).expect_err("the settings are invalid");
        assert!(
            message.contains(test_case.expected_message_fragment),
            "{}: {message}",
            test_case.description
        );
    }
}
