use serde_json::Value;

use crate::sql_lint::tests::helpers::check_dialect_corpus;
use crate::sql_lint::tests::test_types;

const FORMAT_CORPUS: &str = include_str!("fixtures/format_corpus.json");

#[test]
fn given_dialect_corpus_when_formatting_then_output_layout_and_refusals_are_stable()
-> Result<(), String> {
    let test_cases = [
        test_types::FormatCorpusTestCase {
            description: "BigQuery identity corpus",
            dialect: "bigquery",
            expected_formatted: 168,
            expected_refused: 0,
        },
        test_types::FormatCorpusTestCase {
            description: "Databricks identity corpus",
            dialect: "databricks",
            expected_formatted: 62,
            expected_refused: 0,
        },
        test_types::FormatCorpusTestCase {
            description: "DuckDB identity corpus",
            dialect: "duckdb",
            expected_formatted: 178,
            expected_refused: 11,
        },
        test_types::FormatCorpusTestCase {
            description: "PostgreSQL identity corpus",
            dialect: "postgres",
            expected_formatted: 132,
            expected_refused: 5,
        },
        test_types::FormatCorpusTestCase {
            description: "Snowflake identity corpus",
            dialect: "snowflake",
            expected_formatted: 429,
            expected_refused: 6,
        },
        test_types::FormatCorpusTestCase {
            description: "T-SQL identity corpus",
            dialect: "tsql",
            expected_formatted: 75,
            expected_refused: 0,
        },
    ];
    let corpus: Vec<Value> =
        serde_json::from_str(FORMAT_CORPUS).map_err(|error| error.to_string())?;
    for test_case in test_cases {
        let (formatted, refused) = check_dialect_corpus(&corpus, test_case.dialect)?;
        assert_eq!(
            (formatted, refused),
            (test_case.expected_formatted, test_case.expected_refused),
            "{}",
            test_case.description
        );
    }
    Ok(())
}
