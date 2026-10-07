use crate::models::DiscoveryFailure;
use crate::sql_tests::_helpers::scenario_parsing::parse_scenario_file;
use crate::sql_tests::_helpers::test_blocks::parse_sql_test_file;
use crate::sql_tests::models::SqlTestBlock;
use crate::sql_tests::tests::test_types::StatementFileTestCase;

pub(super) type BlockRow = (Vec<String>, String);
pub(super) const FILE_PATH: &str = "project/tests/unit/orders.sql";

fn keys(test_keys: &[&str]) -> Vec<String> {
    test_keys.iter().map(|key| (*key).to_owned()).collect()
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
    parse_sql_test_file(
        FILE_PATH,
        test_case.contents.to_owned(),
        &keys(&["name", "mode", "parameters", "cases"]),
    )
    .map_or_else(failed_rows, |file| {
        (
            file.blocks.iter().map(block_row).collect(),
            file.failure.map(message),
        )
    })
}

/// The scenario file's block row and its failure message.
pub(super) fn scenario_rows(test_case: &StatementFileTestCase) -> (Vec<BlockRow>, Option<String>) {
    parse_scenario_file(
        FILE_PATH,
        test_case.contents.to_owned(),
        &keys(&["description", "tags"]),
    )
    .map_or_else(failed_rows, |file| {
        (
            vec![block_row(&SqlTestBlock {
                header_values: file.header_values,
                sql_body: file.sql_body,
            })],
            None,
        )
    })
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
