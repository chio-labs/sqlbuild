//! Split SQL unit-test contents that are already in memory.

use crate::models::DiscoveryFailure;
use crate::sql_tests::_helpers::test_blocks::parse_sql_test_file;
use crate::sql_tests::models::{DiscoveredSqlTestFile, SqlTestFileOptions};

/// The header-parsed blocks of one SQL test file's contents, named `file_path` in messages.
pub fn parse_sql_test_text(
    file_path: &str,
    contents: String,
    options: &SqlTestFileOptions,
) -> Result<DiscoveredSqlTestFile, DiscoveryFailure> {
    parse_sql_test_file(file_path, contents, options)
}
