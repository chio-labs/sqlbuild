//! Discover, read and header-parse the SQL scenario files under `tests/scenarios/`.

use crate::constants::SQL_SCENARIOS_ROOT;
use crate::models::{DiscoveredFile, ProjectRoot, StageFailure};
use crate::sql_tests::_helpers::scenario_parsing::parse_scenario_file;
use crate::sql_tests::_helpers::selection::discover_sql_files;
use crate::sql_tests::models::{DiscoveredScenarioFile, SqlTestFileOptions};
use crate::tree::models::ProjectTree;

/// Every scenario file in Python's order, header-parsed or failing.
pub fn discover_scenario_files(
    root: &ProjectRoot,
    tree: &ProjectTree,
    options: &SqlTestFileOptions,
) -> Result<Vec<DiscoveredFile<DiscoveredScenarioFile>>, StageFailure> {
    discover_sql_files(root, tree, SQL_SCENARIOS_ROOT, |file_path, contents| {
        parse_scenario_file(file_path, contents, options)
    })
}
