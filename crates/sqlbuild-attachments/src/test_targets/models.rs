//! Targets a SQL test or scenario names, checked against the project's resources.

/// One group of names a model SQL test targets and the phrase Python reports for an unknown one.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct TargetGroup {
    /// For example `mocks unknown model`.
    pub phrase: String,
    pub names: Vec<String>,
    pub known: Vec<String>,
}

/// One scenario CTE and the `__source("name")` references in its body.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ScenarioCteSources {
    pub name: String,
    /// Expected-result and assertion CTEs must not read project sources at all.
    pub check: bool,
    pub sources: Vec<String>,
}
