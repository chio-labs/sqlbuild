use crate::models::DiscoveryFailure;
use crate::sql_tests::main::parse_scenario_text::parse_scenario_text;
use crate::sql_tests::main::parse_sql_test_text::parse_sql_test_text;
use crate::sql_tests::models::{SqlTestBlock, SqlTestFileOptions};
use crate::sql_tests::tests::test_types::StatementFileTestCase;
use sqlbuild_core::text::main::python_text::python_text;

pub(super) type BlockRow = (Vec<String>, String);
pub(super) const FILE_PATH: &str = "project/tests/unit/orders.sql";

fn keys(test_keys: &[&str]) -> Vec<String> {
    test_keys.iter().map(|key| (*key).to_owned()).collect()
}

fn options() -> SqlTestFileOptions {
    SqlTestFileOptions {
        test_keys: keys(&["name", "mode", "parameters", "cases"]),
        scenario_keys: keys(&["description", "tags"]),
        python: python_text((3, 12), "15.0.0").expect("Python 3.12 is supported"),
    }
}

fn block_row(block: &SqlTestBlock) -> BlockRow {
    (
        block
            .header_values
            .iter()
            .map(|(key, _)| key.clone())
            .collect(),
        block.sql_body.clone(),
    )
}

fn message(failure: DiscoveryFailure) -> String {
    failure.message
}

fn failed_rows(failure: DiscoveryFailure) -> (Vec<BlockRow>, Option<String>) {
    (Vec::new(), Some(failure.message))
}

/// The test file's parsed block rows and its failure message.
pub(super) fn test_file_rows(test_case: &StatementFileTestCase) -> (Vec<BlockRow>, Option<String>) {
    parse_sql_test_text(FILE_PATH, test_case.contents.to_owned(), &options()).map_or_else(
        failed_rows,
        |file| {
            (
                file.blocks.iter().map(block_row).collect(),
                file.failure.map(message),
            )
        },
    )
}

/// The scenario file's block row and its failure message.
pub(super) fn scenario_rows(test_case: &StatementFileTestCase) -> (Vec<BlockRow>, Option<String>) {
    parse_scenario_text(FILE_PATH, test_case.contents.to_owned(), &options()).map_or_else(
        failed_rows,
        |file| {
            (
                vec![block_row(&SqlTestBlock {
                    header_values: file.header_values,
                    sql_body: file.sql_body,
                    body_span: (0, 0),
                })],
                None,
            )
        },
    )
}

/// The expected rows in the shape the parsers' rows take.
pub(super) fn expected_rows(
    expected_blocks: &[(&[&str], &str)],
    expected_failure: Option<&str>,
) -> (Vec<BlockRow>, Option<String>) {
    (
        expected_blocks
            .iter()
            .map(|(block_keys, body)| (keys(block_keys), (*body).to_owned()))
            .collect(),
        expected_failure.map(str::to_owned),
    )
}

/// The failure that stops `contents` as a test file and as a scenario file, with their help.
pub(super) fn statement_failures(contents: &str) -> [Option<(String, Option<String>)>; 2] {
    let failure = |failure: DiscoveryFailure| (failure.message, failure.help);
    [
        parse_sql_test_text(FILE_PATH, contents.to_owned(), &options())
            .map_or_else(|stop| Some(failure(stop)), |file| file.failure.map(failure)),
        parse_scenario_text(FILE_PATH, contents.replace("TEST", "SCENARIO"), &options())
            .err()
            .map(failure),
    ]
}
