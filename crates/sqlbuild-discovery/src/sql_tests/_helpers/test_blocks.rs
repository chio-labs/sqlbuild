//! Python's `_split_sql_test_blocks` and the header half of `_parse_single_sql_test_block`.

use crate::_helpers::statement_headers::{StatementHeader, parse_statement_header};
use crate::models::{DiscoveryFailure, FailureKind};
use crate::sql_tests::models::{DiscoveredSqlTestFile, SqlTestBlock, SqlTestFileOptions};
use sqlbuild_core::text::main::is_python_space::is_python_space;
use sqlbuild_core::text::main::python_cleandoc::python_cleandoc;
use sqlbuild_core::text::main::python_strip::python_strip;
use sqlbuild_sqltext::compiler::main::statement_header_matching::match_statement_header;

const TEST_KEYWORD: &str = "TEST";
const TEST_STATEMENT: &str = "TEST()";

/// One `^\s*TEST\s*\(header\)\s*;\s*` match: start, header start, header end and match end.
struct BlockMatch {
    start: usize,
    header_start: usize,
    header_end: usize,
    end: usize,
}

pub(crate) fn parse_sql_test_file(
    file_path: &str,
    contents: String,
    options: &SqlTestFileOptions,
) -> Result<DiscoveredSqlTestFile, DiscoveryFailure> {
    let matches: Vec<BlockMatch> = block_matches(&contents);
    let Some(first) = matches.first() else {
        return Err(missing_header_failure(file_path));
    };
    if !python_strip(&contents[..first.start]).is_empty() {
        return Err(missing_header_failure(file_path));
    }
    let contract = StatementHeader {
        kind: FailureKind::SqlTest,
        statement_name: TEST_KEYWORD,
        statement: TEST_STATEMENT,
        file_path,
        supported_keys: &options.test_keys,
        python: options.python,
    };
    let mut blocks: Vec<SqlTestBlock> = Vec::with_capacity(matches.len());
    let mut failure: Option<DiscoveryFailure> = None;
    for (index, block) in matches.iter().enumerate() {
        let next_start: usize = matches
            .get(index + 1)
            .map_or(contents.len(), |next| next.start);
        let header: &str = &contents[block.header_start..block.header_end];
        let header_line: usize = contents[..block.header_start].matches('\n').count() + 1;
        match parse_statement_header(&contract, header, header_line) {
            Ok(header_values) => blocks.push(SqlTestBlock {
                header_values,
                sql_body: python_cleandoc(
                    options.python,
                    contents[block.end.min(next_start)..next_start]
                        .trim_end_matches(is_python_space),
                ),
            }),
            Err(block_failure) => {
                failure = Some(block_failure);
                break;
            }
        }
    }
    Ok(DiscoveredSqlTestFile {
        contents,
        blocks,
        failure,
    })
}

fn missing_header_failure(file_path: &str) -> DiscoveryFailure {
    DiscoveryFailure::new(
        FailureKind::SqlTest,
        format!(
            "SQL test '{file_path}' must start with a TEST() header as the first non-whitespace \
             content"
        ),
    )
}

/// `_TEST_HEADER_ONLY_PATTERN.finditer(contents)` (MULTILINE): attempts start at line starts.
fn block_matches(contents: &str) -> Vec<BlockMatch> {
    let mut matches: Vec<BlockMatch> = Vec::new();
    let mut position: usize = 0;
    while position <= contents.len() {
        let candidate: usize = next_line_start(contents, position);
        if candidate > contents.len() {
            break;
        }
        match match_statement_header(contents, candidate, TEST_KEYWORD) {
            Some((header_start, header_end, end)) => {
                matches.push(BlockMatch {
                    start: candidate,
                    header_start,
                    header_end,
                    end,
                });
                position = end;
            }
            None => position = candidate + 1,
        }
    }
    matches
}

/// The first position at or after `position` where MULTILINE `^` matches, or past the end.
fn next_line_start(contents: &str, position: usize) -> usize {
    if position == 0 || contents.as_bytes().get(position - 1) == Some(&b'\n') {
        return position;
    }
    contents.as_bytes()[position..]
        .iter()
        .position(|byte| *byte == b'\n')
        .map_or(contents.len() + 1, |offset| position + offset + 1)
}
