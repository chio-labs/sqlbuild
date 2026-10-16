//! Plan output fields gathered across the plan phases before the output is built once.

use pyo3::prelude::{Bound, PyAny};

/// The plan output's fields and metadata entries, each set before the output is built.
#[derive(Debug)]
pub(crate) struct PlanOutputFields<'py> {
    pub(crate) fields: Vec<(&'static str, Bound<'py, PyAny>)>,
    pub(crate) metadata: Vec<(&'static str, Bound<'py, PyAny>)>,
}

/// The model changes and resolved actions after write-hash reconciliation.
#[derive(Debug)]
pub(crate) struct ChangeReconciliation<'py> {
    pub(crate) changes: Bound<'py, PyAny>,
    pub(crate) resolved_actions: Bound<'py, PyAny>,
}

/// Planned model entries and the warnings planning them raised.
#[derive(Debug)]
pub(crate) struct ModelEntryResults<'py> {
    pub(crate) entries: Vec<Bound<'py, PyAny>>,
    pub(crate) warnings: Vec<Bound<'py, PyAny>>,
}
