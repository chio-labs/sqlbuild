use polyglot_sql::DialectType;

use crate::lineage::main::parser_dialect::parser_dialect;
use crate::lineage::tests::test_types::RichDialectTestCase;

/// Every `PolyglotAnalysisDialect` value resolves as the wheel's serde decoding did.
#[test]
fn given_analysis_dialect_names_when_resolving_then_match_the_wheel_decoding() {
    let test_cases = [
        RichDialectTestCase {
            description: "every PolyglotAnalysisDialect value",
            names: &[
                "generic",
                "postgresql",
                "mysql",
                "bigquery",
                "snowflake",
                "duckdb",
                "sqlite",
                "hive",
                "spark",
                "trino",
                "presto",
                "redshift",
                "tsql",
                "oracle",
                "clickhouse",
                "databricks",
                "athena",
                "teradata",
                "doris",
                "starrocks",
                "materialize",
                "risingwave",
                "singlestore",
                "cockroachdb",
                "tidb",
                "druid",
                "solr",
                "tableau",
                "dune",
                "fabric",
                "drill",
                "dremio",
                "exasol",
                "datafusion",
            ],
            expected_known: true,
        },
        RichDialectTestCase {
            description: "a name no dialect carries",
            names: &["orders_sql"],
            expected_known: false,
        },
    ];
    for test_case in test_cases {
        for name in test_case.names {
            let decoded: Option<DialectType> =
                serde_json::from_value(serde_json::Value::String((*name).to_owned())).ok();
            assert_eq!(parser_dialect(Some(name)), decoded, "{name}");
            assert_eq!(
                decoded.is_some(),
                test_case.expected_known,
                "{}: {name}",
                test_case.description
            );
        }
    }
}
