//! Discover, read and split the SQL unit-test files under `tests/unit/`.

use crate::constants::SQL_TESTS_ROOT;
use crate::models::{DiscoveredFile, ProjectRoot, StageFailure};
use crate::sql_tests::_helpers::selection::discover_sql_files;
use crate::sql_tests::_helpers::test_blocks::parse_sql_test_file;
use crate::sql_tests::models::{DiscoveredSqlTestFile, SqlTestFileOptions};
use crate::tree::models::ProjectTree;

/// Every SQL test file in Python's order, split into header-parsed blocks or failing.
pub fn discover_sql_test_files(
    root: &ProjectRoot,
    tree: &ProjectTree,
    options: &SqlTestFileOptions,
) -> Result<Vec<DiscoveredFile<DiscoveredSqlTestFile>>, StageFailure> {
    discover_sql_files(
        root,
        tree,
        &SQL_TESTS_ROOT.join("/"),
        |file_path, contents| parse_sql_test_file(file_path, contents, options),
    )
}
