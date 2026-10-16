//! Plan output fields gathered across the plan phases before the output is built once.

use pyo3::prelude::{Bound, PyAny};

/// The plan output's fields and metadata entries, each set before the output is built.
#[derive(Debug)]
pub(crate) struct PlanOutputFields<'py> {
    pub(crate) fields: Vec<(&'static str, Bound<'py, PyAny>)>,
    pub(crate) metadata: Vec<(&'static str, Bound<'py, PyAny>)>,
}
