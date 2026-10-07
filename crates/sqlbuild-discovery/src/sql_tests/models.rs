//! Native results for SQL unit-test and scenario files.

use crate::models::DiscoveryFailure;
use sqlbuild_sqltext::compiler::models::AuthoredValue;

/// The keys each statement header supports, passed from Python's constants.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SqlTestFileOptions {
    pub test_keys: Vec<String>,
    pub scenario_keys: Vec<String>,
}

/// One `TEST(...)` block whose header parsed with only supported keys.
#[derive(Clone, Debug, PartialEq)]
pub struct SqlTestBlock {
    pub header_values: Vec<(String, AuthoredValue)>,
    /// `inspect.cleandoc` of the SQL after the header.
    pub sql_body: String,
}

/// A test file split into blocks; parsing stops at the first block whose header fails.
#[derive(Clone, Debug, PartialEq)]
pub struct DiscoveredSqlTestFile {
    pub contents: String,
    pub blocks: Vec<SqlTestBlock>,
    pub failure: Option<DiscoveryFailure>,
}

/// A scenario file whose header parsed with only supported keys.
#[derive(Clone, Debug, PartialEq)]
pub struct DiscoveredScenarioFile {
    pub contents: String,
    pub header_values: Vec<(String, AuthoredValue)>,
    pub sql_body: String,
}
