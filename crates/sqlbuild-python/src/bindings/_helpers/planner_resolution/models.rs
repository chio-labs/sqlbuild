//! Typed requests of planner SQL resolution.

use pyo3::prelude::{Bound, PyAny};

/// The cursor window that filters the cursor inputs one resolution reads.
#[derive(Debug)]
pub(crate) struct CursorFiltering<'py> {
    pub(crate) bounds: Bound<'py, PyAny>,
    pub(crate) filter_inputs: Bound<'py, PyAny>,
    pub(crate) cursor_type: Bound<'py, PyAny>,
    pub(crate) lower_bound_inclusive: bool,
}

/// One model's SQL resolution decisions.
#[derive(Debug)]
pub(crate) struct ModelSqlRequest<'py> {
    pub(crate) model: Bound<'py, PyAny>,
    pub(crate) snapshot: Bound<'py, PyAny>,
    pub(crate) backfill: Bound<'py, PyAny>,
    pub(crate) full_refresh: bool,
    pub(crate) cursor_overrides: (Bound<'py, PyAny>, Bound<'py, PyAny>),
    pub(crate) replaces_relation: bool,
    pub(crate) full_rebuild_cause: Option<String>,
}
