//! Ingestr destination URIs and command lines match the Python integration's.

use crate::ingestr_command::main::format_ingestr_command::format_ingestr_command;
use crate::ingestr_command::main::ingestr_command_arguments::ingestr_command_arguments;
use crate::ingestr_command::main::ingestr_destination_table::ingestr_destination_table;
use crate::ingestr_command::main::ingestr_destination_uri::ingestr_destination_uri;
use crate::ingestr_command::models::{IngestrDestination, IngestrSource};
use crate::ingestr_command::tests::test_types::{CommandTestCase, DestinationUriTestCase};
use crate::loader_connection::models::LoaderConnection;

#[test]
fn given_connection_when_building_destination_uri_then_matches_python_quoting() {
    let test_cases = [
        DestinationUriTestCase {
            description: "duckdb path",
            adapter_name: "duckdb",
            strings: &[("database", " warehouse.duckdb ")],
            port: None,
            expected_uri: Ok("duckdb:///warehouse.duckdb"),
        },
        DestinationUriTestCase {
            description: "motherduck prefix and token",
            adapter_name: "motherduck",
            strings: &[("database", "md:my db/é"), ("token", "t o/k=n&")],
            port: None,
            expected_uri: Ok("motherduck://my%20db/%C3%A9?token=t+o%2Fk%3Dn%26"),
        },
        DestinationUriTestCase {
            description: "postgres with sslmode and port",
            adapter_name: "postgres",
            strings: &[
                ("user", "ana lyst"),
                ("password", "p@ss:/w"),
                ("dbname", "orders"),
            ],
            port: Some("6543"),
            expected_uri: Ok("postgresql://ana%20lyst:p%40ss%3A/w@localhost:6543/orders"),
        },
        DestinationUriTestCase {
            description: "sqlserver defaults",
            adapter_name: "sqlserver",
            strings: &[("password", "Sqlbuild!2026"), ("database", "analytics")],
            port: None,
            expected_uri: Ok("mssql://sa:Sqlbuild%212026@localhost:1433/analytics\
                 ?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"),
        },
        DestinationUriTestCase {
            description: "snowflake requires an account",
            adapter_name: "snowflake",
            strings: &[("account", "  ")],
            port: None,
            expected_uri: Err(
                "Adapter 'snowflake' requires connection.account for ingestr integration loaders",
            ),
        },
        DestinationUriTestCase {
            description: "unsupported adapter",
            adapter_name: "fabric",
            strings: &[],
            port: None,
            expected_uri: Err("Adapter 'fabric' does not support ingestr integration loaders"),
        },
    ];
    for test_case in test_cases {
        let connection: LoaderConnection = LoaderConnection {
            strings: test_case
                .strings
                .iter()
                .map(|(key, value)| ((*key).to_owned(), (*value).to_owned()))
                .collect(),
            port: test_case.port.map(str::to_owned),
        };
        let uri: Result<String, String> =
            ingestr_destination_uri(test_case.adapter_name, &connection)
                .map_err(|error| error.message);
        assert_eq!(
            uri.as_deref().map_err(String::as_str),
            test_case.expected_uri,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_source_when_building_command_then_orders_arguments_like_python() {
    let test_cases = [
        CommandTestCase {
            description: "reload with schema",
            schema: Some("raw"),
            is_reload: true,
            expected_display: "ingestr ingest --source-uri 'csv://a b' --source-table t \
                 --dest-uri duckdb:///w.duckdb --dest-table raw.orders --yes --progress log \
                 --primary-key id --full-refresh '--note=it'\"'\"'s'",
        },
        CommandTestCase {
            description: "incremental without schema",
            schema: None,
            is_reload: false,
            expected_display: "ingestr ingest --source-uri 'csv://a b' --source-table t \
                 --dest-uri duckdb:///w.duckdb --dest-table orders --yes --progress log \
                 --primary-key id '--note=it'\"'\"'s'",
        },
    ];
    let source: IngestrSource = IngestrSource {
        source_uri: "csv://a b".to_owned(),
        source_table: "t".to_owned(),
        primary_key: vec!["id".to_owned()],
        extra_args: vec!["--note=it's".to_owned()],
        ..IngestrSource::default()
    };
    for test_case in test_cases {
        let destination: IngestrDestination = IngestrDestination {
            uri: "duckdb:///w.duckdb".to_owned(),
            table: ingestr_destination_table(test_case.schema, "orders"),
            is_reload: test_case.is_reload,
        };
        assert_eq!(
            format_ingestr_command(&ingestr_command_arguments(&source, &destination)),
            test_case.expected_display,
            "{}",
            test_case.description
        );
    }
}
