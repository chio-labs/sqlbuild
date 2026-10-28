use crate::settings::models::{AuditEvidence, RecallSettings, StoreLocation, StorePurpose};
use crate::settings::tests::helpers::{
    central_store, defaults, local_store, resolution_error, resolved,
};
use crate::settings::tests::test_types::{
    ErrorKindTestCase, ResolveErrorTestCase, ResolveTestCase,
};

const DEFAULT_PROJECT: &[(&str, &str)] = &[(
    "sqlbuild_project.toml",
    "name = \"shop\"\nadapter = \"duckdb\"\ndefault_target = \"dev\"\n[targets.dev]\nschema = \"analytics\"\n",
)];

const LAYERED_PROJECT: &[(&str, &str)] = &[
    (
        "sqlbuild_project.toml",
        "name = \"shop\"\nadapter = \"duckdb\"\n\
         [recall]\nretention = \"10d\"\nwrite_connection = \"history\"\nread_connection = \"history\"\n\
         [connections.history]\nadapter = \"sqlite\"\npath = \"state/history.sqlite3\"\n\
         [connections.central]\nadapter = \"clickhouse\"\nhost = \"localhost\"\n\
         database = \"observability\"\npassword = \"secret\"\n\
         [connections.other]\nadapter = \"postgres\"\nhost = \"localhost\"\n\
         [targets.dev]\n[targets.dev.recall]\nenabled = false\n\
         [targets.prod]\n[targets.prod.recall]\nwrite_connection = \"central\"\nread_connection = \"central\"\n\
         [targets.capped]\n[targets.capped.recall]\nwrite_connection = \"central\"\nread_connection = \"central\"\n\
         max_output_bytes = 4096\naudit_evidence = \"error\"\n\
         [targets.qa]\n[targets.qa.recall]\nwrite_connection = \"other\"\nread_connection = \"other\"\n\
         [targets.laptop]\n[targets.laptop.recall]\nread_connection = \"central\"\n",
    ),
    (
        "sqlbuild_local.toml",
        "[recall]\nshutdown_timeout = \"1s\"\n[connections.history]\npath = \"/tmp/opencode/elsewhere.sqlite3\"\n",
    ),
];

const READER_PROJECT: &[(&str, &str)] = &[(
    "sqlbuild_project.toml",
    "name = \"shop\"\nadapter = \"duckdb\"\n[recall]\nread_connection = \"central\"\n\
     [connections.central]\nadapter = \"clickhouse\"\nhost = \"localhost\"\n\
     database = \"observability\"\npassword = \"secret\"\n",
)];

const OUTPUT_LIMIT_PROJECT: &[(&str, &str)] = &[(
    "sqlbuild_project.toml",
    "name = \"shop\"\nadapter = \"duckdb\"\n[recall]\nmax_output_bytes = 0\n\
     [targets.dev]\n[targets.dev.recall]\nmax_output_bytes = 8388608\n[targets.prod]\n",
)];

const WRITER_CREDENTIALS_PROJECT: &[(&str, &str)] = &[(
    "sqlbuild_project.toml",
    "name = \"shop\"\nadapter = \"duckdb\"\n\
     [recall]\nwrite_connection = \"central\"\nread_connection = \"reader\"\n\
     [connections.central]\nadapter = \"clickhouse\"\nhost = \"localhost\"\n\
     database = \"observability\"\npassword = \"secret\"\n\
     [connections.reader]\nadapter = \"clickhouse\"\nhost = \"localhost\"\n\
     database = \"observability\"\npassword = \"${env:SQLBUILD_RECALL_READER_UNSET_FOR_TEST}\"\n",
)];

const READER_CREDENTIALS_PROJECT: &[(&str, &str)] = &[(
    "sqlbuild_project.toml",
    "name = \"shop\"\nadapter = \"duckdb\"\n\
     [recall]\nwrite_connection = \"writer\"\nread_connection = \"central\"\n\
     [connections.writer]\nadapter = \"clickhouse\"\nhost = \"localhost\"\n\
     database = \"observability\"\npassword = \"${env:SQLBUILD_RECALL_WRITER_UNSET_FOR_TEST}\"\n\
     [connections.central]\nadapter = \"clickhouse\"\nhost = \"localhost\"\n\
     database = \"observability\"\npassword = \"secret\"\n",
)];

const LOCAL_READ_PROJECT: &[(&str, &str)] = &[
    (
        "sqlbuild_project.toml",
        "name = \"shop\"\nadapter = \"duckdb\"\n[recall]\nwrite_connection = \"central\"\n\
         [connections.central]\nadapter = \"clickhouse\"\nhost = \"localhost\"\n\
         database = \"observability\"\npassword = \"secret\"\n",
    ),
    (
        "sqlbuild_local.toml",
        "[recall]\nread_connection = \"central\"\n",
    ),
];

const TARGET_WRITE_PROJECT: &[(&str, &str)] = &[(
    "sqlbuild_project.toml",
    "name = \"shop\"\nadapter = \"duckdb\"\n[recall]\nread_connection = \"central\"\n\
     [connections.central]\nadapter = \"clickhouse\"\nhost = \"localhost\"\n\
     database = \"observability\"\npassword = \"secret\"\n\
     [targets.ci]\n[targets.ci.recall]\nwrite_connection = \"central\"\n",
)];

#[test]
fn given_project_layers_when_resolved_then_target_over_local_over_project_over_defaults() {
    let test_cases = [
        ResolveTestCase {
            description: "without a recall section local SQLite is on by default",
            files: DEFAULT_PROJECT,
            target: None,
            purpose: StorePurpose::Record,
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
            purpose: StorePurpose::Record,
            expected_settings: RecallSettings {
                enabled: false,
                target: Some("dev".to_owned()),
                store: StoreLocation::Sqlite {
                    path: "/tmp/opencode/elsewhere.sqlite3".into(),
                },
                write_connection: Some("history".to_owned()),
                read_connection: Some("history".to_owned()),
                retention_days: 10,
                shutdown_timeout_ms: 1000,
                ..defaults()
            },
        },
        ResolveTestCase {
            description: "a ClickHouse connection keeps its options and records all output by default",
            files: LAYERED_PROJECT,
            target: Some("prod"),
            purpose: StorePurpose::Record,
            expected_settings: RecallSettings {
                target: Some("prod".to_owned()),
                store: central_store(),
                write_connection: Some("central".to_owned()),
                read_connection: Some("central".to_owned()),
                retention_days: 10,
                shutdown_timeout_ms: 1000,
                max_output_bytes: None,
                ..defaults()
            },
        },
        ResolveTestCase {
            description: "a configured output limit and audit evidence mode apply to one target",
            files: LAYERED_PROJECT,
            target: Some("capped"),
            purpose: StorePurpose::Record,
            expected_settings: RecallSettings {
                target: Some("capped".to_owned()),
                store: central_store(),
                write_connection: Some("central".to_owned()),
                read_connection: Some("central".to_owned()),
                retention_days: 10,
                shutdown_timeout_ms: 1000,
                max_output_bytes: Some(4096),
                audit_evidence: AuditEvidence::Error,
                ..defaults()
            },
        },
        ResolveTestCase {
            description: "a target raises the output limit over the project's unlimited one",
            files: OUTPUT_LIMIT_PROJECT,
            target: Some("dev"),
            purpose: StorePurpose::Record,
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
            purpose: StorePurpose::Record,
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
            purpose: StorePurpose::Record,
            expected_settings: RecallSettings {
                target: Some("qa".to_owned()),
                store: StoreLocation::Unsupported {
                    connection: "other".to_owned(),
                    adapter: "postgres".to_owned(),
                },
                write_connection: Some("other".to_owned()),
                read_connection: Some("other".to_owned()),
                retention_days: 10,
                shutdown_timeout_ms: 1000,
                max_output_bytes: None,
                ..defaults()
            },
        },
        ResolveTestCase {
            description: "a target read connection replaces only the read side",
            files: LAYERED_PROJECT,
            target: Some("laptop"),
            purpose: StorePurpose::Record,
            expected_settings: RecallSettings {
                target: Some("laptop".to_owned()),
                store: StoreLocation::Sqlite {
                    path: "/tmp/opencode/elsewhere.sqlite3".into(),
                },
                write_connection: Some("history".to_owned()),
                read_connection: Some("central".to_owned()),
                retention_days: 10,
                shutdown_timeout_ms: 1000,
                max_output_bytes: Some(2 * 1024 * 1024),
                ..defaults()
            },
        },
        ResolveTestCase {
            description: "a read connection alone reads shared history and writes the local store",
            files: READER_PROJECT,
            target: None,
            purpose: StorePurpose::Record,
            expected_settings: RecallSettings {
                store: local_store(),
                read_connection: Some("central".to_owned()),
                ..defaults()
            },
        },
        ResolveTestCase {
            description: "a reader resolves the read connection a target sets",
            files: LAYERED_PROJECT,
            target: Some("laptop"),
            purpose: StorePurpose::Read,
            expected_settings: RecallSettings {
                target: Some("laptop".to_owned()),
                store: central_store(),
                write_connection: Some("history".to_owned()),
                read_connection: Some("central".to_owned()),
                retention_days: 10,
                shutdown_timeout_ms: 1000,
                max_output_bytes: None,
                ..defaults()
            },
        },
        ResolveTestCase {
            description: "a reader with a read connection alone reads shared history",
            files: READER_PROJECT,
            target: None,
            purpose: StorePurpose::Read,
            expected_settings: RecallSettings {
                store: central_store(),
                read_connection: Some("central".to_owned()),
                max_output_bytes: None,
                ..defaults()
            },
        },
        ResolveTestCase {
            description: "a recording machine needs only the writer's environment",
            files: WRITER_CREDENTIALS_PROJECT,
            target: None,
            purpose: StorePurpose::Record,
            expected_settings: RecallSettings {
                store: central_store(),
                write_connection: Some("central".to_owned()),
                read_connection: Some("reader".to_owned()),
                max_output_bytes: None,
                ..defaults()
            },
        },
        ResolveTestCase {
            description: "a reader needs only the reader's environment",
            files: READER_CREDENTIALS_PROJECT,
            target: None,
            purpose: StorePurpose::Read,
            expected_settings: RecallSettings {
                store: central_store(),
                write_connection: Some("writer".to_owned()),
                read_connection: Some("central".to_owned()),
                max_output_bytes: None,
                ..defaults()
            },
        },
        ResolveTestCase {
            description: "a local read connection completes a project write connection",
            files: LOCAL_READ_PROJECT,
            target: None,
            purpose: StorePurpose::Record,
            expected_settings: RecallSettings {
                store: central_store(),
                write_connection: Some("central".to_owned()),
                read_connection: Some("central".to_owned()),
                max_output_bytes: None,
                ..defaults()
            },
        },
        ResolveTestCase {
            description: "a target's write connection is completed by the project's read connection",
            files: TARGET_WRITE_PROJECT,
            target: Some("ci"),
            purpose: StorePurpose::Record,
            expected_settings: RecallSettings {
                target: Some("ci".to_owned()),
                store: central_store(),
                write_connection: Some("central".to_owned()),
                read_connection: Some("central".to_owned()),
                max_output_bytes: None,
                ..defaults()
            },
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            resolved(test_case.files, test_case.target, test_case.purpose),
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
                "name = \"x\"\nadapter = \"duckdb\"\n[recall]\nwrite_connection = \"local\"\nread_connection = \"missing\"\n[connections.local]\npath = \"a.sqlite3\"\nadapter = \"sqlite\"\n",
            )],
            target: None,
            purpose: StorePurpose::Read,
            expected_message_fragment: "recall.read_connection names unknown connection 'missing'",
        },
        ResolveErrorTestCase {
            description: "target settings are named with their path",
            files: &[(
                "sqlbuild_project.toml",
                "name = \"x\"\nadapter = \"duckdb\"\n[targets.dev.recall]\nretention = \"soon\"\n",
            )],
            target: Some("dev"),
            purpose: StorePurpose::Record,
            expected_message_fragment: "targets.dev.recall.retention",
        },
        ResolveErrorTestCase {
            description: "an unset environment reference in a ClickHouse connection is named",
            files: &[(
                "sqlbuild_project.toml",
                "name = \"x\"\nadapter = \"duckdb\"\n[recall]\nread_connection = \"central\"\n\
                 [connections.central]\nadapter = \"clickhouse\"\n\
                 password = \"${env:SQLBUILD_RECALL_UNSET_FOR_TEST}\"\n",
            )],
            target: None,
            purpose: StorePurpose::Read,
            expected_message_fragment: "connections.central.password references unset",
        },
        ResolveErrorTestCase {
            description: "a reader without the reader's environment names it",
            files: WRITER_CREDENTIALS_PROJECT,
            target: None,
            purpose: StorePurpose::Read,
            expected_message_fragment: "connections.reader.password references unset",
        },
        ResolveErrorTestCase {
            description: "a recording machine without the writer's environment names it",
            files: READER_CREDENTIALS_PROJECT,
            target: None,
            purpose: StorePurpose::Record,
            expected_message_fragment: "connections.writer.password references unset",
        },
        ResolveErrorTestCase {
            description: "a write connection without a read connection anywhere is rejected",
            files: &[(
                "sqlbuild_project.toml",
                "name = \"x\"\nadapter = \"duckdb\"\n[targets.ci.recall]\nwrite_connection = \"local\"\n\
                 [connections.local]\npath = \"a.sqlite3\"\nadapter = \"sqlite\"\n",
            )],
            target: Some("ci"),
            purpose: StorePurpose::Read,
            expected_message_fragment: "recall.write_connection requires recall.read_connection for target `ci`",
        },
    ];

    for test_case in test_cases {
        let message: String = resolved(test_case.files, test_case.target, test_case.purpose)
            .expect_err("the settings are invalid");
        assert!(
            message.contains(test_case.expected_message_fragment),
            "{}: {message}",
            test_case.description
        );
    }
}

#[test]
fn given_a_write_connection_problem_when_recording_then_only_mistakes_fail_the_command() {
    let test_cases = [
        ErrorKindTestCase {
            description: "a misspelled write connection is a configuration mistake",
            files: &[(
                "sqlbuild_project.toml",
                "name = \"x\"\nadapter = \"duckdb\"\n[recall]\nwrite_connection = \"histroy_writer\"\n\
                 read_connection = \"history\"\n[connections.history]\nadapter = \"sqlite\"\npath = \"h.sqlite3\"\n",
            )],
            expected_fragment: "recall.write_connection names unknown connection 'histroy_writer'",
            expected_invalid_configuration: true,
        },
        ErrorKindTestCase {
            description: "a SQLite write connection without a path is a configuration mistake",
            files: &[(
                "sqlbuild_project.toml",
                "name = \"x\"\nadapter = \"duckdb\"\n[recall]\nwrite_connection = \"history\"\n\
                 read_connection = \"history\"\n[connections.history]\nadapter = \"sqlite\"\n",
            )],
            expected_fragment: "connections.history.path must name the SQLite file",
            expected_invalid_configuration: true,
        },
        ErrorKindTestCase {
            description: "an unset writer variable only skips recording",
            files: READER_CREDENTIALS_PROJECT,
            expected_fragment: "connections.writer.password references unset",
            expected_invalid_configuration: false,
        },
    ];

    for test_case in test_cases {
        let (message, invalid) = resolution_error(test_case.files, None, StorePurpose::Record)
            .expect("the settings do not resolve");
        assert_eq!(
            (message.contains(test_case.expected_fragment), invalid),
            (true, test_case.expected_invalid_configuration),
            "{}: {message}",
            test_case.description
        );
    }
}
