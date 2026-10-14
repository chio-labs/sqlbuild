//! Scenario graph input and output values.

use std::collections::{BTreeSet, HashMap, HashSet};

use crate::assembly::project::types::ObjectKey;

/// Authored scenario names and project dependency facts in declaration order.
#[derive(Debug, Default)]
pub struct ScenarioGraphInput {
    pub name: String,
    pub expected: Vec<String>,
    pub assertions: Vec<String>,
    pub targets: Vec<String>,
    pub refs: Vec<String>,
    pub sources: Vec<String>,
    pub seeds: Vec<String>,
    pub dbt_refs: Vec<String>,
    pub models: HashMap<String, Vec<ObjectKey>>,
    pub project_sources: HashSet<String>,
    pub project_seeds: HashSet<String>,
}

/// Required scenario relations and diagnostics in observable order.
#[derive(Debug, Default)]
pub struct ScenarioGraphOutput {
    pub models: BTreeSet<String>,
    pub refs: BTreeSet<String>,
    pub sources: BTreeSet<String>,
    pub seeds: BTreeSet<String>,
    pub seed_fixtures: BTreeSet<String>,
    pub dbt_refs: BTreeSet<String>,
    pub functions: Vec<ObjectKey>,
    pub warnings: Vec<(String, bool)>,
}
