//! Scenario graph cases.

use crate::planner_scenario::models::ScenarioGraphInput;

pub(super) struct GraphTestCase {
    pub description: &'static str,
    pub input: ScenarioGraphInput,
    pub expected_models: Vec<&'static str>,
    pub expected_refs: Vec<&'static str>,
    pub expected_functions: Vec<(&'static str, &'static str)>,
    pub expected_warnings: Vec<(&'static str, bool)>,
}
#[derive(Debug)]
pub(super) struct MarkerTestCase {
    pub description: &'static str,
    pub sql: &'static str,
    pub kind: usize,
    pub scanned: bool,
    pub expected_sql: Result<&'static str, &'static str>,
}
