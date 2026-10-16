//! Typed requests of SQL-test planning.

use pyo3::prelude::{Bound, PyAny};

/// How one batch of SQL tests is planned.
#[derive(Debug)]
pub(crate) struct SqlTestPlanOptions<'py> {
    pub(crate) sql_analysis_enabled: Bound<'py, PyAny>,
    pub(crate) render_sql: bool,
    pub(crate) include_plan: bool,
    pub(crate) artifact: bool,
}

/// How assembling SQL-test plan results validates fixtures.
#[derive(Debug)]
pub(crate) struct SqlTestAssembly<'py> {
    pub(crate) sql_analysis_enabled: Bound<'py, PyAny>,
    pub(crate) validate_fixtures: bool,
    pub(crate) fixture_planning_context: Bound<'py, PyAny>,
}
