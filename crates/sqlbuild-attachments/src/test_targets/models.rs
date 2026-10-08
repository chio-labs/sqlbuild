//! Targets a SQL test or scenario names, checked against the project's resources.

use std::collections::HashSet;

/// The project's model, source, seed, table function and macro names, built once per compile.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct TargetCatalog {
    pub models: HashSet<String>,
    pub sources: HashSet<String>,
    pub seeds: HashSet<String>,
    pub table_functions: HashSet<String>,
    pub macros: HashSet<String>,
}

/// The names one model SQL test targets, in Python's validation order.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct TestTargets {
    pub mock_models: Vec<String>,
    pub mock_sources: Vec<String>,
    pub mock_seeds: Vec<String>,
    pub mock_table_functions: Vec<String>,
    pub macro_mocks: Vec<String>,
    pub expected_models: Vec<String>,
    pub assertion_targets: Vec<String>,
}

/// One scenario CTE and the `__source("name")` references in its body.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ScenarioCteSources {
    pub name: String,
    /// Expected-result and assertion CTEs must not read project sources at all.
    pub check: bool,
    pub sources: Vec<String>,
}
