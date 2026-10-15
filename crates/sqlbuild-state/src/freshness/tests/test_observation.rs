use crate::freshness::main::configuration_error::configuration_error;
use crate::freshness::main::read_latest_sql::read_latest_sql;
use crate::freshness::main::relevant_sources_sql::relevant_sources_sql;
use crate::freshness::main::single_value_problem::single_value_problem;
use crate::freshness::models::QueryShape;
use crate::freshness::tests::test_types::{
    ConfigurationErrorTestCase, ReadLatestTestCase, RelevantSourcesTestCase, SingleValueTestCase,
};

#[test]
fn given_qualified_name_when_reading_latest_then_ranks_newest_row_per_identity() {
    let test_cases = [ReadLatestTestCase {
        description: "one schema-qualified state table",
        qualified_name: "main.state",
        expected_sql: "SELECT source_name, target_database, target_schema, target_name, run_id, \
strategy, value_kind, data_version, data_version_hash, observed_at FROM (SELECT source_name, \
target_database, target_schema, target_name, run_id, strategy, value_kind, data_version, \
data_version_hash, observed_at, ROW_NUMBER() OVER (PARTITION BY source_name, target_database, \
target_schema, target_name ORDER BY observed_at DESC, run_id DESC) AS __sqlbuild_latest_rank \
FROM main.state) AS __sqlbuild_latest_source_freshness WHERE __sqlbuild_latest_rank = 1",
    }];

    for test_case in test_cases {
        assert_eq!(
            read_latest_sql(test_case.qualified_name),
            test_case.expected_sql,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_source_names_when_narrowing_latest_read_then_quotes_each_literal() {
    let test_cases = [
        RelevantSourcesTestCase {
            description: "one plain name",
            source_names: &["orders"],
            expected_sql: "SELECT * FROM (R) AS __sqlbuild_relevant WHERE source_name IN ('orders')",
        },
        RelevantSourcesTestCase {
            description: "quotes are doubled",
            source_names: &["a", "o'b"],
            expected_sql: "SELECT * FROM (R) AS __sqlbuild_relevant WHERE source_name IN ('a', 'o''b')",
        },
    ];

    for test_case in test_cases {
        let names: Vec<String> = test_case
            .source_names
            .iter()
            .map(|name| (*name).to_owned())
            .collect();

        assert_eq!(
            relevant_sources_sql("R", &names),
            test_case.expected_sql,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_query_shape_when_checking_single_value_then_reports_first_problem() {
    let test_cases = [
        SingleValueTestCase {
            description: "two columns win over two rows",
            shape: QueryShape {
                columns: 2,
                rows: 2,
                first_value_null: false,
            },
            expected_problem: Some("source 's' freshness query must return exactly one column"),
        },
        SingleValueTestCase {
            description: "no rows",
            shape: QueryShape {
                columns: 1,
                rows: 0,
                first_value_null: false,
            },
            expected_problem: Some("source 's' freshness query must return exactly one row"),
        },
        SingleValueTestCase {
            description: "a null value",
            shape: QueryShape {
                columns: 1,
                rows: 1,
                first_value_null: true,
            },
            expected_problem: Some("source 's' freshness data_version cannot be null"),
        },
        SingleValueTestCase {
            description: "one value",
            shape: QueryShape {
                columns: 1,
                rows: 1,
                first_value_null: false,
            },
            expected_problem: None,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            single_value_problem("s", test_case.shape).as_deref(),
            test_case.expected_problem,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_observation_message_when_classifying_then_configuration_errors_are_detected() {
    let test_cases = [
        ConfigurationErrorTestCase {
            description: "physical table requirement",
            message: "source 's' adapter freshness requires a physical table source",
            expected_configuration_error: true,
        },
        ConfigurationErrorTestCase {
            description: "incomplete configuration",
            message: "source 's' has incomplete sql freshness configuration",
            expected_configuration_error: true,
        },
        ConfigurationErrorTestCase {
            description: "query failure",
            message: "source 's' freshness query failed: boom",
            expected_configuration_error: false,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            configuration_error(test_case.message),
            test_case.expected_configuration_error,
            "{}",
            test_case.description
        );
    }
}
