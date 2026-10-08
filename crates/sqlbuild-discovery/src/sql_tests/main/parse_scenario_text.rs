//! Header-parse SQL scenario contents that are already in memory.

use crate::_helpers::pool::on_discovery_pool;
use crate::models::DiscoveryFailure;
use crate::sql_tests::_helpers::scenario_parsing::parse_scenario_file;
use crate::sql_tests::models::{DiscoveredScenarioFile, SqlTestFileOptions};

/// The parsed header and body of one scenario file's contents, named `file_path` in messages, parsed on the discovery pool.
pub fn parse_scenario_text(
    file_path: &str,
    contents: String,
    options: &SqlTestFileOptions,
) -> Result<DiscoveredScenarioFile, DiscoveryFailure> {
    on_discovery_pool(|| parse_scenario_file(file_path, contents, options))
}
